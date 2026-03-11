#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHIRPS V3 Data Extractor - Módulo de extração de dados NetCDF
=============================================================
Extrai precipitação de arquivos NetCDF do CHIRPS V3.0 (byYear)
Fonte: https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/byYear/

Autor: Sistema Paramétrico V3 - dagrofic
Versão: 3.0.0
"""

import warnings
import logging
import os
import re
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURAÇÕES GLOBAIS
# ============================================================================

CHIRPS_V3_BASE_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/byYear/"
CHIRPS_V3_ANNUAL_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/byYear/"

# Nomes possíveis de arquivo CHIRPS V3
def get_chirps_v3_filename_annual(year: int) -> str:
    """Retorna nome do arquivo anual CHIRPS V3"""
    return f"chirps-v3.0.rnl.{year}.days_p05.nc"

def get_chirps_v3_filename_monthly(year: int, month: int) -> str:
    """Retorna nome do arquivo mensal CHIRPS V3"""
    return f"chirps-v3.0.rnl.{year}.{month:02d}.days_p05.nc"

def get_chirps_v3_url_annual(year: int) -> str:
    """Retorna URL de download do arquivo anual"""
    return f"{CHIRPS_V3_ANNUAL_URL}{get_chirps_v3_filename_annual(year)}"

def get_chirps_v3_url_monthly(year: int, month: int) -> str:
    """Retorna URL de download do arquivo mensal"""
    return f"{CHIRPS_V3_BASE_URL}{get_chirps_v3_filename_monthly(year, month)}"


# ============================================================================
# FUNÇÕES DE ABERTURA DE NetCDF
# ============================================================================

def open_nc(path: str):
    """
    Abre arquivo NetCDF com fallback automático entre engines.
    Suporta h5netcdf, netcdf4 e scipy.
    """
    import xarray as xr
    last_err = None
    for eng in ("h5netcdf", "netcdf4", "scipy"):
        try:
            return xr.open_dataset(path, engine=eng, use_cftime=False)
        except Exception:
            try:
                return xr.open_dataset(path, engine=eng, use_cftime=True)
            except Exception as e:
                last_err = e
    raise RuntimeError(f"Falha ao abrir {path}: {last_err}")


def detect_coord_names(ds) -> tuple:
    """Detecta nomes de coordenadas automaticamente"""
    lat_name = next((c for c in ("latitude", "lat", "y") if c in ds.coords or c in ds.dims), None)
    lon_name = next((c for c in ("longitude", "lon", "x") if c in ds.coords or c in ds.dims), None)
    time_name = "time" if ("time" in ds.coords or "time" in ds.dims) else None
    if lat_name is None or lon_name is None or time_name is None:
        raise ValueError(f"Coordenadas não reconhecidas. Disponíveis: {list(ds.coords)}")
    return lat_name, lon_name, time_name


def detect_var_name(ds) -> str:
    """Detecta variável de precipitação no dataset"""
    for cand in ("precip", "precipitation", "rain", "rf", "p"):
        if cand in ds.data_vars:
            return cand
    vars_list = list(ds.data_vars)
    if vars_list:
        return vars_list[0]
    raise ValueError("Nenhuma variável de precipitação encontrada")


def adjust_lon_if_needed(ds, lon_name: str, target_lon: float) -> float:
    """
    Ajusta longitude se o dataset usa 0-360 em vez de -180 a +180.
    CHIRPS V3 usa coordenadas -180 a +180, mas verifica por segurança.
    """
    try:
        lon_vals = ds[lon_name]
        lon_min, lon_max = float(lon_vals.min()), float(lon_vals.max())
    except Exception:
        return target_lon
    if lon_min >= 0 and lon_max > 180 and target_lon < 0:
        adjusted = target_lon % 360
        logger.info(f"Longitude ajustada de {target_lon} para {adjusted} (sistema 0-360)")
        return adjusted
    return target_lon


def file_time_span(ds, time_name: str) -> tuple:
    """Retorna período coberto pelo arquivo como (min_date, max_date)"""
    t = ds[time_name]
    return pd.to_datetime(str(t.min().values)), pd.to_datetime(str(t.max().values))


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distância em km entre dois pontos geográficos (fórmula Haversine)"""
    r = 6371.0088
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return float(r * c)


# ============================================================================
# EXTRAÇÃO DE PONTO ÚNICO
# ============================================================================

def extract_point_from_nc(ds, source_file: str, 
                           target_lat: float, target_lon: float,
                           required_start: str, required_end: str) -> pd.DataFrame:
    """
    Extrai série temporal de precipitação para um ponto específico.
    
    Args:
        ds: xarray.Dataset aberto
        source_file: Nome do arquivo fonte (para auditoria)
        target_lat: Latitude contratual
        target_lon: Longitude contratual
        required_start: Data inicial (YYYY-MM-DD)
        required_end: Data final (YYYY-MM-DD)
    
    Returns:
        DataFrame com colunas: time, latitude, longitude, precip, 
                                pixel_latitude, pixel_longitude, distance_km, source_file
    """
    lat_name, lon_name, time_name = detect_coord_names(ds)
    var_name = detect_var_name(ds)
    lon_adj = adjust_lon_if_needed(ds, lon_name, target_lon)

    # Extração pelo método nearest (pixel mais próximo)
    da = (
        ds[var_name]
        .sel({lat_name: target_lat, lon_name: lon_adj}, method="nearest")
        .sel({time_name: slice(required_start, required_end)})
    )

    df = da.to_dataframe().reset_index()

    # Renomear coordenadas para colunas de auditoria
    rename_map = {}
    if lat_name in df.columns:
        rename_map[lat_name] = "pixel_latitude"
    if lon_name in df.columns:
        rename_map[lon_name] = "pixel_longitude"
    if time_name in df.columns:
        rename_map[time_name] = "time"
    df = df.rename(columns=rename_map)

    # Renomear variável de precipitação se necessário
    if var_name != "precip" and var_name in df.columns:
        df = df.rename(columns={var_name: "precip"})

    # Proteção: retornar DataFrame vazio com schema correto se vazio
    required_cols = ["time", "latitude", "longitude", "precip",
                     "pixel_latitude", "pixel_longitude", "distance_km", "source_file"]
    if df.empty:
        return pd.DataFrame(columns=required_cols)

    # Adicionar coordenadas contratuais (ponto exato do contrato)
    df["latitude"] = target_lat
    df["longitude"] = target_lon

    # Calcular distância entre ponto contratual e pixel CHIRPS para auditoria
    if "pixel_latitude" in df.columns and "pixel_longitude" in df.columns:
        df["distance_km"] = df.apply(
            lambda row: haversine_distance(
                row["latitude"], row["longitude"],
                row["pixel_latitude"], row["pixel_longitude"]
            ), axis=1
        )
    else:
        df["distance_km"] = 0.0

    df["source_file"] = source_file

    # Ordenar e retornar colunas relevantes
    keep = [c for c in required_cols if c in df.columns]
    return df[keep]


# ============================================================================
# PROCESSAMENTO MULTI-ARQUIVO (FUNÇÃO PRINCIPAL)
# ============================================================================

def extract_chirps_v3(
    files: list,
    target_lat: float,
    target_lon: float,
    required_start: str,
    required_end: str,
    data_dir: str = None
) -> dict:
    """
    Processa múltiplos arquivos NetCDF e extrai série de precipitação.
    
    Args:
        files: Lista de caminhos absolutos ou nomes de arquivo
        target_lat: Latitude contratual
        target_lon: Longitude contratual
        required_start: Data inicial (YYYY-MM-DD)
        required_end: Data final (YYYY-MM-DD)
        data_dir: Diretório base para busca de arquivos (opcional)
    
    Returns:
        dict com: 
          - df: DataFrame com dados completos
          - audit_df: DataFrame de auditoria por arquivo
          - gaps_df: DataFrame de lacunas detectadas
          - total_precip: precipitação total no período
          - missing_days: número de dias sem dados
          - status: 'ok' ou 'partial' ou 'error'
    """
    dfs = []
    audit_rows = []

    logger.info(f"Iniciando extração CHIRPS V3: {required_start} → {required_end}")
    logger.info(f"Ponto: LAT={target_lat}, LON={target_lon}")

    for fpath_orig in files:
        fpath = fpath_orig

        # Se não existe, tentar no data_dir
        if not Path(fpath).exists() and data_dir:
            candidate = Path(data_dir) / Path(fpath_orig).name
            if candidate.exists():
                fpath = str(candidate)

        p = Path(fpath)
        if not p.exists():
            logger.warning(f"Arquivo não encontrado: {p}")
            audit_rows.append({
                "arquivo": p.name,
                "status": "ausente",
                "variavel_lida": None,
                "unidade": None,
                "inicio_no_arquivo": None,
                "fim_no_arquivo": None,
                "dias_extraidos": 0,
                "observacao": f"Caminho: {fpath}"
            })
            continue

        try:
            ds = open_nc(str(p))
            try:
                lat_name, lon_name, time_name = detect_coord_names(ds)
                var_name = detect_var_name(ds)
                tmin, tmax = file_time_span(ds, time_name)
                units = ds[var_name].attrs.get("units", "mm/day")

                df_part = extract_point_from_nc(
                    ds, p.name, target_lat, target_lon, 
                    required_start, required_end
                )

                if not df_part.empty:
                    dfs.append(df_part)

                audit_rows.append({
                    "arquivo": p.name,
                    "status": "ok",
                    "variavel_lida": var_name,
                    "unidade": units,
                    "inicio_no_arquivo": tmin.strftime("%Y-%m-%d"),
                    "fim_no_arquivo": tmax.strftime("%Y-%m-%d"),
                    "dias_extraidos": len(df_part),
                    "observacao": f"Pixel: LAT={df_part['pixel_latitude'].iloc[0]:.5f}, LON={df_part['pixel_longitude'].iloc[0]:.5f}" if not df_part.empty else "Sem dados no período"
                })
                logger.info(f"[OK] {p.name} → {len(df_part)} dias extraídos")

            finally:
                ds.close()

        except Exception as e:
            logger.error(f"Erro em {p.name}: {e}")
            audit_rows.append({
                "arquivo": p.name,
                "status": f"erro: {str(e)}",
                "variavel_lida": None,
                "unidade": None,
                "inicio_no_arquivo": None,
                "fim_no_arquivo": None,
                "dias_extraidos": 0,
                "observacao": str(e)
            })

    # Montar DataFrames de resultado
    audit_df = pd.DataFrame(audit_rows)

    if not dfs:
        return {
            "df": pd.DataFrame(),
            "audit_df": audit_df,
            "gaps_df": pd.DataFrame(),
            "total_precip": 0.0,
            "missing_days": 0,
            "status": "error",
            "message": "Nenhum arquivo encontrado ou nenhum dado extraído."
        }

    full_df = pd.concat(dfs, ignore_index=True)
    full_df["time"] = pd.to_datetime(full_df["time"])
    full_df = full_df.sort_values("time").drop_duplicates(subset=["time"])
    full_df = full_df.reset_index(drop=True)

    # Garantir que precip seja float e tratar valores negativos/NaN
    full_df["precip"] = pd.to_numeric(full_df["precip"], errors="coerce").fillna(0.0)
    full_df.loc[full_df["precip"] < 0, "precip"] = 0.0

    # Detectar lacunas
    expected_days = pd.date_range(start=required_start, end=required_end, freq="D")
    existing_days = pd.to_datetime(full_df["time"]).dt.normalize()
    missing_days_list = expected_days.difference(existing_days)
    gaps_df = pd.DataFrame({"dias_ausentes": missing_days_list})

    total_precip = float(full_df["precip"].sum())
    missing_days = len(missing_days_list)

    status = "ok" if missing_days == 0 else "partial"
    if missing_days > 7:
        status = "partial_critical"

    logger.info(f"Total precipitação: {total_precip:.2f} mm")
    logger.info(f"Lacunas detectadas: {missing_days} dias")

    return {
        "df": full_df,
        "audit_df": audit_df,
        "gaps_df": gaps_df,
        "total_precip": total_precip,
        "missing_days": missing_days,
        "status": status,
        "message": f"Extração concluída: {len(full_df)} dias, {total_precip:.2f} mm total"
    }


# ============================================================================
# EXPORTAÇÃO PARA EXCEL
# ============================================================================

def export_to_excel(result: dict, output_path: str,
                    target_lat: float, target_lon: float,
                    required_start: str, required_end: str,
                    strike_mm: float = None, exit_mm: float = None,
                    limit_brl: float = None, tick_brl: float = None,
                    deductible_pct: float = 0,
                    policy_info: dict = None) -> str:
    """
    Exporta resultado da extração para Excel no formato padrão INVESTPREV.
    
    Formato: 3 abas - dados, auditoria_arquivos, auditoria_lacunas
    """
    from openpyxl import Workbook
    from openpyxl.styles import (PatternFill, Font, Alignment, Border, Side,
                                  numbers)
    from openpyxl.utils import get_column_letter

    df = result.get("df", pd.DataFrame())
    audit_df = result.get("audit_df", pd.DataFrame())
    gaps_df = result.get("gaps_df", pd.DataFrame())
    total_precip = result.get("total_precip", 0.0)

    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Usar pandas ExcelWriter para simplicidade e compatibilidade
    with pd.ExcelWriter(str(out_path), engine="openpyxl") as writer:
        # ─── Aba DADOS ─────────────────────────────────────────────────────
        if not df.empty:
            export_df = df[["time", "latitude", "longitude", "precip",
                            "pixel_latitude", "pixel_longitude",
                            "distance_km", "source_file"]].copy()
            export_df["time"] = pd.to_datetime(export_df["time"]).dt.strftime("%Y-%m-%d")
            export_df["precip"] = export_df["precip"].round(6)
            export_df["distance_km"] = export_df["distance_km"].round(6)

            # Adicionar linha de total
            total_row = pd.DataFrame([{
                "time": "TOTAL",
                "latitude": target_lat,
                "longitude": target_lon,
                "precip": total_precip,
                "pixel_latitude": export_df["pixel_latitude"].iloc[0] if len(export_df) > 0 else "",
                "pixel_longitude": export_df["pixel_longitude"].iloc[0] if len(export_df) > 0 else "",
                "distance_km": "",
                "source_file": "CHIRPS V3.0"
            }])
            export_df = pd.concat([export_df, total_row], ignore_index=True)
            export_df.to_excel(writer, sheet_name="dados", index=False)
        else:
            pd.DataFrame(columns=["time", "latitude", "longitude", "precip",
                                   "pixel_latitude", "pixel_longitude",
                                   "distance_km", "source_file"]).to_excel(
                writer, sheet_name="dados", index=False)

        # ─── Aba AUDITORIA ARQUIVOS ─────────────────────────────────────────
        audit_df.to_excel(writer, sheet_name="auditoria_arquivos", index=False)

        # ─── Aba AUDITORIA LACUNAS ──────────────────────────────────────────
        gaps_df.to_excel(writer, sheet_name="auditoria_lacunas", index=False)

        # ─── Aba RESUMO PARAMÉTRICO ─────────────────────────────────────────
        if strike_mm is not None:
            total_precip_val = total_precip
            deficit = max(0, strike_mm - total_precip_val)
            triggered = total_precip_val < strike_mm

            # Calcular indenização
            payout_bruto = deficit * (tick_brl or 0)
            payout_limitado = min(payout_bruto, limit_brl or float('inf'))
            franquia = (limit_brl or 0) * (deductible_pct / 100)
            payout_final = max(0, payout_limitado - franquia)

            summary_data = [
                ["RESUMO REGULAÇÃO PARAMÉTRICA - CHIRPS V3.0", ""],
                ["", ""],
                ["FONTE DE DADOS", "CHIRPS V3.0 (CHC-UCSB)"],
                ["URL FONTE", CHIRPS_V3_ANNUAL_URL],
                ["TIPO DE COBERTURA", "Déficit de Precipitação"],
                ["", ""],
                ["PARÂMETROS CONTRATUAIS", ""],
                ["Período Início", required_start],
                ["Período Fim", required_end],
                ["Latitude Contratual", target_lat],
                ["Longitude Contratual", target_lon],
                ["Strike (mm)", strike_mm],
                ["Exit Point (mm)", exit_mm or 0],
                ["Limit (BRL)", limit_brl or "N/A"],
                ["Tick (BRL/mm)", tick_brl or "N/A"],
                ["Franquia (%)", deductible_pct],
                ["", ""],
                ["RESULTADO", ""],
                ["Precipitação Total Observada (mm)", round(total_precip_val, 4)],
                ["Strike (mm)", strike_mm],
                ["Déficit (mm)", round(deficit, 4)],
                ["Sinistro Acionado", "✅ SIM" if triggered else "❌ NÃO"],
                ["Indenização Bruta (BRL)", round(payout_bruto, 2) if tick_brl else "N/A"],
                ["Franquia (BRL)", round(franquia, 2) if limit_brl else "N/A"],
                ["Indenização Final (BRL)", round(payout_final, 2) if tick_brl else "N/A"],
            ]

            if policy_info:
                summary_data.extend([
                    ["", ""],
                    ["DADOS DA APÓLICE", ""],
                    ["Segurado", policy_info.get("insured", "")],
                    ["Apólice Nº", policy_info.get("policy_number", "")],
                    ["Período Apólice", policy_info.get("period", "")],
                ])

            summary_df = pd.DataFrame(summary_data, columns=["Parâmetro", "Valor"])
            summary_df.to_excel(writer, sheet_name="resumo_parametrico", index=False)

    logger.info(f"Excel exportado: {out_path}")
    return str(out_path)


# ============================================================================
# DOWNLOAD AUTOMÁTICO
# ============================================================================

def download_chirps_v3_file(year: int, data_dir: str,
                             month: int = None,
                             force: bool = False,
                             progress_callback=None) -> dict:
    """
    Faz download de arquivo CHIRPS V3 para diretório local.
    
    Tenta primeiro arquivo anual, depois mensal.
    
    Args:
        year: Ano a baixar
        data_dir: Diretório destino
        month: Mês específico (None = arquivo anual)
        force: Forçar re-download mesmo se arquivo existe
        progress_callback: Função callback(bytes_done, total_bytes)
    
    Returns:
        dict: {success, path, size_mb, message}
    """
    import requests

    dest_dir = Path(data_dir) / str(year)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if month:
        fname = get_chirps_v3_filename_monthly(year, month)
        url = get_chirps_v3_url_monthly(year, month)
    else:
        fname = get_chirps_v3_filename_annual(year)
        url = get_chirps_v3_url_annual(year)

    dest_path = dest_dir / fname

    # Verificar se já existe e está completo
    if dest_path.exists() and not force:
        size_mb = dest_path.stat().st_size / 1024 / 1024
        if size_mb > 1:  # Mínimo 1MB para ser válido
            logger.info(f"Arquivo já existe: {dest_path} ({size_mb:.1f} MB)")
            return {
                "success": True,
                "path": str(dest_path),
                "size_mb": size_mb,
                "message": f"Arquivo existente: {fname} ({size_mb:.1f} MB)"
            }

    logger.info(f"Baixando: {url}")

    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        chunk_size = 1024 * 1024  # 1MB chunks

        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded, total_size)

        size_mb = dest_path.stat().st_size / 1024 / 1024
        logger.info(f"Download concluído: {fname} ({size_mb:.1f} MB)")

        return {
            "success": True,
            "path": str(dest_path),
            "size_mb": size_mb,
            "message": f"Download concluído: {fname} ({size_mb:.1f} MB)"
        }

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            msg = f"Arquivo não disponível ainda: {fname} (404)"
        else:
            msg = f"Erro HTTP {e.response.status_code}: {fname}"
        logger.error(msg)
        if dest_path.exists():
            dest_path.unlink()
        return {"success": False, "path": None, "size_mb": 0, "message": msg}

    except Exception as e:
        msg = f"Erro no download de {fname}: {str(e)}"
        logger.error(msg)
        if dest_path.exists():
            dest_path.unlink()
        return {"success": False, "path": None, "size_mb": 0, "message": msg}


def check_and_update_data(data_dir: str, years: list = None,
                           progress_callback=None) -> list:
    """
    Verifica e atualiza arquivos CHIRPS V3 para os anos necessários.
    Regra: Atualiza arquivo do ano atual após dia 15 de cada mês.
    
    Args:
        data_dir: Diretório base dos dados
        years: Lista de anos a verificar (None = automático)
        progress_callback: Callback de progresso
    
    Returns:
        Lista de resultados de download
    """
    today = datetime.now()
    current_year = today.year
    current_month = today.month
    current_day = today.day

    if years is None:
        # Sempre manter: ano atual e ano anterior
        years = [current_year - 1, current_year]
        # Se chegamos ao ano seguinte (ex: 2027), não precisamos mais de 2025
        # Manter apenas os últimos 2 anos relevantes

    results = []

    for year in years:
        annual_path = Path(data_dir) / str(year) / get_chirps_v3_filename_annual(year)

        # Para o ano atual: verificar se deve atualizar (após dia 15)
        if year == current_year:
            if annual_path.exists():
                # Verificar se o arquivo está desatualizado
                # (criado antes do mês atual e estamos após dia 15)
                file_mtime = datetime.fromtimestamp(annual_path.stat().st_mtime)
                months_since_update = (today.year - file_mtime.year) * 12 + (today.month - file_mtime.month)

                if months_since_update >= 1 and current_day >= 15:
                    logger.info(f"Atualizando {year} (mês {current_month}, dia {current_day} >= 15)")
                    result = download_chirps_v3_file(
                        year, data_dir, force=True,
                        progress_callback=progress_callback
                    )
                    results.append(result)
                else:
                    logger.info(f"Arquivo {year} em dia: {annual_path}")
                    results.append({
                        "success": True,
                        "path": str(annual_path),
                        "size_mb": annual_path.stat().st_size / 1024 / 1024,
                        "message": f"Arquivo {year} atual"
                    })
            else:
                # Baixar se ainda não existe
                if current_day >= 15 or current_month > 1:
                    result = download_chirps_v3_file(
                        year, data_dir,
                        progress_callback=progress_callback
                    )
                    results.append(result)

        else:
            # Anos anteriores: apenas baixar se não existir
            if not annual_path.exists():
                result = download_chirps_v3_file(
                    year, data_dir,
                    progress_callback=progress_callback
                )
                results.append(result)
            else:
                size_mb = annual_path.stat().st_size / 1024 / 1024
                results.append({
                    "success": True,
                    "path": str(annual_path),
                    "size_mb": size_mb,
                    "message": f"Arquivo {year} disponível ({size_mb:.1f} MB)"
                })

    return results


def find_chirps_files_for_period(data_dir: str, 
                                  start_date: str, 
                                  end_date: str) -> list:
    """
    Encontra arquivos CHIRPS V3 necessários para cobrir o período.
    
    Retorna lista de caminhos de arquivo absolutos.
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    years_needed = list(range(start_dt.year, end_dt.year + 1))
    files = []

    for year in years_needed:
        # Preferir arquivo anual
        annual_path = Path(data_dir) / str(year) / get_chirps_v3_filename_annual(year)
        if annual_path.exists():
            files.append(str(annual_path))
        else:
            # Tentar arquivos mensais
            months_needed = []
            if year == start_dt.year and year == end_dt.year:
                months_needed = list(range(start_dt.month, end_dt.month + 1))
            elif year == start_dt.year:
                months_needed = list(range(start_dt.month, 13))
            elif year == end_dt.year:
                months_needed = list(range(1, end_dt.month + 1))
            else:
                months_needed = list(range(1, 13))

            for month in months_needed:
                monthly_path = Path(data_dir) / str(year) / get_chirps_v3_filename_monthly(year, month)
                if monthly_path.exists():
                    files.append(str(monthly_path))

    return files


# ============================================================================
# UTILITÁRIOS DE STATUS
# ============================================================================

def get_data_status(data_dir: str) -> dict:
    """
    Retorna status dos arquivos CHIRPS V3 disponíveis localmente.
    """
    status = {}
    data_path = Path(data_dir)

    if not data_path.exists():
        return {"error": f"Diretório não encontrado: {data_dir}"}

    for year_dir in sorted(data_path.iterdir()):
        if not year_dir.is_dir():
            continue
        try:
            year = int(year_dir.name)
        except ValueError:
            continue

        year_files = {}
        for nc_file in sorted(year_dir.glob("*.nc")):
            size_mb = nc_file.stat().st_size / 1024 / 1024
            mtime = datetime.fromtimestamp(nc_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            year_files[nc_file.name] = {
                "size_mb": round(size_mb, 1),
                "last_modified": mtime,
                "valid": size_mb > 0.5
            }

        status[year] = year_files

    return status
