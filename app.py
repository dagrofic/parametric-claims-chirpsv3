#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sistema de Regulação de Sinistros Paramétricos - CHIRPS V3.0
=============================================================
Interface Web Flask para processamento de apólices paramétricas
com dados CHIRPS V3.0 via arquivos NetCDF locais.

Fonte de dados: https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/

Autor: Sistema Paramétrico V3 - dagrofic
Versão: 3.0.0
"""

import os
import json
import logging
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import (Flask, render_template, request, jsonify, 
                   send_file, redirect, url_for)

from chirps_v3_extractor import (
    extract_chirps_v3, 
    extract_chirps_v3_with_tif_fallback,
    find_chirps_files_for_period,
    download_chirps_v3_file,
    check_and_update_data,
    get_data_status,
    export_to_excel,
    get_chirps_v3_filename_annual,
    CHIRPS_V3_ANNUAL_URL,
    POLICY_NC_FILE
)
from html_parser import parse_html_content, calculate_parametric_claim

# ============================================================================
# CONFIGURAÇÃO
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# Diretório de dados CHIRPS V3
DATA_DIR = os.environ.get("CHIRPS_DATA_DIR", "./data/chirps_v3")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chirps-v3-parametric-2025")

# Sistema de tarefas assíncronas (download em background)
_tasks: dict = {}
_tasks_lock = threading.Lock()


# ============================================================================
# ROTAS PRINCIPAIS
# ============================================================================

@app.route("/")
def index():
    """Página principal - Sistema de regulação"""
    return render_template("index.html",
                           chirps_url=CHIRPS_V3_ANNUAL_URL,
                           data_dir=DATA_DIR)


@app.route("/admin")
def admin():
    """Painel de administração - status e download de dados"""
    status = get_data_status(DATA_DIR)
    return render_template("admin.html", 
                           data_status=status,
                           data_dir=DATA_DIR,
                           chirps_url=CHIRPS_V3_ANNUAL_URL)


# ============================================================================
# API - PROCESSAMENTO DE REGULAÇÃO
# ============================================================================

@app.route("/api/process", methods=["POST"])
def api_process():
    """
    Processa regulação de sinistro paramétrico.
    
    Recebe HTML da apólice, extrai parâmetros, busca dados CHIRPS V3,
    calcula resultado e retorna JSON completo.
    """
    try:
        data = request.get_json(force=True)
        html_content = data.get("html", "")

        if not html_content.strip():
            return jsonify({"error": "Conteúdo HTML não fornecido"}), 400

        # 1. Extrair parâmetros do HTML
        params = parse_html_content(html_content)
        logger.info(f"Parâmetros extraídos: {params}")

        # Validar parâmetros obrigatórios
        missing = [k for k in ["period_start", "period_end"] 
                   if not params.get(k)]
        if missing:
            return jsonify({
                "error": f"Parâmetros não encontrados no HTML: {', '.join(missing)}. "
                         f"Verifique se o HTML contém 'Period cover : From : YYYY-MM-DD to : YYYY-MM-DD'"
            }), 400

        if not params.get("latitude") or not params.get("longitude"):
            return jsonify({
                "error": "Coordenadas não encontradas no HTML. "
                         "O sistema buscará chirps_lat/chirps_lon na tabela de clustering."
            }), 400

        period_start = params["period_start"]
        period_end = params["period_end"]
        lat = float(params["latitude"])
        lon = float(params["longitude"])

        # 2. Encontrar arquivos CHIRPS V3 necessários
        files = find_chirps_files_for_period(DATA_DIR, period_start, period_end)

        # Verificar se há NetCDF de período da apólice disponível
        has_policy_nc = os.path.exists(POLICY_NC_FILE)
        
        if not files and not has_policy_nc:
            # Tentar baixar automaticamente
            from datetime import datetime as dt
            start_year = int(period_start[:4])
            end_year = int(period_end[:4])
            years_needed = list(range(start_year, end_year + 1))
            
            return jsonify({
                "error": "Arquivos CHIRPS V3 não encontrados localmente.",
                "action_required": "download",
                "years_needed": years_needed,
                "message": (
                    f"É necessário fazer o download dos dados CHIRPS V3 para os anos "
                    f"{', '.join(map(str, years_needed))}. "
                    f"Acesse o painel Admin ou use o botão 'Baixar Dados' abaixo."
                )
            }), 404

        # 3. Extrair dados CHIRPS V3 (com suporte a TIF/NetCDF de apólice)
        result = extract_chirps_v3_with_tif_fallback(
            files=files,
            target_lat=lat,
            target_lon=lon,
            required_start=period_start,
            required_end=period_end,
            data_dir=DATA_DIR,
            use_policy_nc=True
        )

        if result["status"] == "error":
            return jsonify({
                "error": f"Falha na extração: {result.get('message', 'Erro desconhecido')}",
                "audit": result.get("audit_df", {}).to_dict() if hasattr(result.get("audit_df"), "to_dict") else {}
            }), 500

        # 4. Calcular sinistro
        total_precip = result["total_precip"]
        strike = params.get("strike")
        claim_result = {}

        if strike is not None:
            claim_result = calculate_parametric_claim(
                total_value=total_precip,
                type_of_cover=params.get("type_of_cover", "precipitation"),
                strike=float(strike),
                exit_point=float(params.get("exit_point", 0)),
                limit=float(params.get("limit", 0)),
                tick=float(params.get("tick", 0)),
                deductible_pct=float(params.get("deductible_pct", 0))
            )

        # 5. Montar resposta
        df = result["df"]
        daily_data = []
        if not df.empty:
            for _, row in df.iterrows():
                daily_data.append({
                    "date": str(row["time"])[:10],
                    "precip": round(float(row["precip"]), 4),
                    "pixel_lat": round(float(row.get("pixel_latitude", lat)), 6),
                    "pixel_lon": round(float(row.get("pixel_longitude", lon)), 6),
                    "distance_km": round(float(row.get("distance_km", 0)), 4)
                })

        audit_data = []
        audit_df = result.get("audit_df")
        if audit_df is not None and not audit_df.empty:
            for _, row in audit_df.iterrows():
                audit_data.append({k: str(v) if v is not None else "" 
                                   for k, v in row.items()})

        # Extrair pixel coords do primeiro dado disponível
        pixel_lat_val = None
        pixel_lon_val = None
        if daily_data:
            pixel_lat_val = daily_data[0].get("pixel_lat")
            pixel_lon_val = daily_data[0].get("pixel_lon")

        return jsonify({
            "success": True,
            "params": params,
            # Coordenadas contratuais (exatas do HTML) - nível raiz para facilitar acesso
            "latitude": lat,
            "longitude": lon,
            # Pixel CHIRPS usado na extração
            "pixel_latitude": pixel_lat_val,
            "pixel_longitude": pixel_lon_val,
            "daily_data": daily_data,
            "total_precip": round(total_precip, 4),
            "missing_days": result["missing_days"],
            "data_status": result["status"],
            "claim": claim_result,
            "audit": audit_data,
            "files_used": [Path(f).name for f in files],
            "chirps_version": "V3.0",
            "source_url": CHIRPS_V3_ANNUAL_URL
        })

    except Exception as e:
        logger.error(f"Erro em /api/process: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    """
    Recalcula sinistro com parâmetros personalizados.
    Útil quando usuário altera Limit, Tick ou Franquia na interface.
    """
    try:
        data = request.get_json(force=True)

        total_precip = float(data.get("total_precip", 0))
        type_of_cover = data.get("type_of_cover", "precipitation")
        strike = float(data.get("strike", 0))
        exit_point = float(data.get("exit_point", 0))
        limit = float(data.get("limit", 0))
        tick = float(data.get("tick", 0))
        deductible_pct = float(data.get("deductible_pct", 0))

        claim = calculate_parametric_claim(
            total_value=total_precip,
            type_of_cover=type_of_cover,
            strike=strike,
            exit_point=exit_point,
            limit=limit,
            tick=tick,
            deductible_pct=deductible_pct
        )

        return jsonify({"success": True, "claim": claim})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-excel", methods=["POST"])
def api_download_excel():
    """Gera e retorna arquivo Excel com dados completos da regulação"""
    try:
        data = request.get_json(force=True)
        html_content = data.get("html", "")
        total_precip = data.get("total_precip")
        daily_data_raw = data.get("daily_data", [])
        claim = data.get("claim", {})
        params = data.get("params", {})

        if not params:
            params = parse_html_content(html_content) if html_content else {}

        # Reconstruir DataFrames para exportação
        import pandas as pd
        df_export = pd.DataFrame(daily_data_raw)
        if not df_export.empty:
            df_export = df_export.rename(columns={
                "date": "time",
                "pixel_lat": "pixel_latitude",
                "pixel_lon": "pixel_longitude"
            })
            # Adicionar colunas obrigatórias se ausentes (dados vindos do frontend)
            lat = params.get("latitude", 0)
            lon = params.get("longitude", 0)
            if "latitude" not in df_export.columns:
                df_export["latitude"] = lat
            if "longitude" not in df_export.columns:
                df_export["longitude"] = lon
            if "source_file" not in df_export.columns:
                df_export["source_file"] = "CHIRPS V3.0"
            if "distance_km" not in df_export.columns:
                df_export["distance_km"] = 0.0
            if "pixel_latitude" not in df_export.columns:
                df_export["pixel_latitude"] = lat
            if "pixel_longitude" not in df_export.columns:
                df_export["pixel_longitude"] = lon

        # Gerar Excel temporário
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False, 
                                          prefix="chirps_v3_") as tmp:
            output_path = tmp.name

        # Exportar
        result_dict = {
            "df": df_export,
            "audit_df": pd.DataFrame(),
            "gaps_df": pd.DataFrame(),
            "total_precip": total_precip or 0.0
        }

        export_to_excel(
            result=result_dict,
            output_path=output_path,
            target_lat=params.get("latitude", 0),
            target_lon=params.get("longitude", 0),
            required_start=params.get("period_start", ""),
            required_end=params.get("period_end", ""),
            strike_mm=params.get("strike"),
            exit_mm=params.get("exit_point", 0),
            limit_brl=params.get("limit"),
            tick_brl=params.get("tick"),
            deductible_pct=params.get("deductible_pct", 0),
            policy_info={
                "insured": params.get("insured", ""),
                "policy_date": params.get("policy_date", ""),
                "period": f"{params.get('period_start','')} a {params.get('period_end','')}"
            }
        )

        insured = params.get("insured", "regulacao").replace(" ", "_")[:30]
        period = f"{params.get('period_start','')[:7]}".replace("-", "_")
        filename = f"CHIRPS_V3_{insured}_{period}.xlsx"

        return send_file(
            output_path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logger.error(f"Erro ao gerar Excel: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ============================================================================
# API - GERENCIAMENTO DE DADOS
# ============================================================================

@app.route("/api/data/status", methods=["GET"])
def api_data_status():
    """Retorna status dos arquivos CHIRPS V3 disponíveis"""
    status = get_data_status(DATA_DIR)
    
    # Calcular total de armazenamento
    total_size = 0.0
    total_files = 0
    for year_data in status.values():
        if isinstance(year_data, dict):
            for fname, finfo in year_data.items():
                if isinstance(finfo, dict) and finfo.get("valid"):
                    total_size += finfo.get("size_mb", 0)
                    total_files += 1

    return jsonify({
        "success": True,
        "data_dir": DATA_DIR,
        "chirps_source": CHIRPS_V3_ANNUAL_URL,
        "files": status,
        "total_size_mb": round(total_size, 1),
        "total_files": total_files
    })


@app.route("/api/data/download", methods=["POST"])
def api_data_download():
    """
    Inicia download de arquivo(s) CHIRPS V3 em background.
    Retorna task_id para polling de status.
    """
    try:
        data = request.get_json(force=True)
        year = int(data.get("year", datetime.now().year))
        force = bool(data.get("force", False))

        task_id = str(uuid.uuid4())

        with _tasks_lock:
            _tasks[task_id] = {
                "type": "download",
                "status": "pending",
                "message": f"Iniciando download CHIRPS V3 {year}...",
                "progress": 0,
                "result": None,
                "error": None,
                "year": year,
                "started_at": datetime.now().isoformat()
            }

        def run_download(tid, yr, frc):
            def progress_cb(done, total):
                pct = int(done / total * 100) if total > 0 else 0
                size_done = done / 1024 / 1024
                size_total = total / 1024 / 1024
                with _tasks_lock:
                    _tasks[tid]["progress"] = pct
                    _tasks[tid]["message"] = (
                        f"Baixando {yr}: {size_done:.1f} MB / {size_total:.1f} MB ({pct}%)"
                    )

            with _tasks_lock:
                _tasks[tid]["status"] = "running"

            result = download_chirps_v3_file(
                year=yr,
                data_dir=DATA_DIR,
                force=frc,
                progress_callback=progress_cb
            )

            with _tasks_lock:
                if result["success"]:
                    _tasks[tid]["status"] = "completed"
                    _tasks[tid]["progress"] = 100
                    _tasks[tid]["message"] = result["message"]
                    _tasks[tid]["result"] = result
                else:
                    _tasks[tid]["status"] = "error"
                    _tasks[tid]["error"] = result["message"]
                    _tasks[tid]["message"] = result["message"]

        t = threading.Thread(target=run_download, args=(task_id, year, force), daemon=True)
        t.start()

        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": f"Download de {year} iniciado"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/data/update", methods=["POST"])
def api_data_update():
    """
    Verifica e atualiza todos os arquivos CHIRPS V3 necessários.
    Implementa a regra: após dia 15 de cada mês, atualiza ano corrente.
    """
    try:
        task_id = str(uuid.uuid4())
        data = request.get_json(force=True) or {}
        years = data.get("years")

        with _tasks_lock:
            _tasks[task_id] = {
                "type": "update",
                "status": "pending",
                "message": "Verificando arquivos CHIRPS V3...",
                "progress": 0,
                "result": None,
                "error": None,
                "started_at": datetime.now().isoformat()
            }

        def run_update(tid, yrs):
            with _tasks_lock:
                _tasks[tid]["status"] = "running"

            results = check_and_update_data(DATA_DIR, years=yrs)

            with _tasks_lock:
                _tasks[tid]["status"] = "completed"
                _tasks[tid]["progress"] = 100
                _tasks[tid]["result"] = results
                success_count = sum(1 for r in results if r.get("success"))
                _tasks[tid]["message"] = (
                    f"Atualização concluída: {success_count}/{len(results)} arquivos OK"
                )

        t = threading.Thread(target=run_update, args=(task_id, years), daemon=True)
        t.start()

        return jsonify({
            "success": True,
            "task_id": task_id,
            "message": "Verificação de atualização iniciada"
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/task/<task_id>", methods=["GET"])
def api_task_status(task_id):
    """Retorna status de uma tarefa em background"""
    with _tasks_lock:
        task = _tasks.get(task_id)

    if not task:
        return jsonify({"error": "Tarefa não encontrada"}), 404

    return jsonify({
        "task_id": task_id,
        "status": task["status"],
        "message": task["message"],
        "progress": task.get("progress", 0),
        "result": task.get("result"),
        "error": task.get("error"),
        "type": task.get("type")
    })


# ============================================================================
# STARTUP
# ============================================================================

def ensure_data_dir():
    """Garante que o diretório de dados existe"""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    current_year = datetime.now().year
    for year in [current_year - 1, current_year]:
        (Path(DATA_DIR) / str(year)).mkdir(parents=True, exist_ok=True)
    logger.info(f"Diretório de dados: {Path(DATA_DIR).absolute()}")


if __name__ == "__main__":
    ensure_data_dir()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    logger.info(f"Iniciando CHIRPS V3 Paramétrico na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
