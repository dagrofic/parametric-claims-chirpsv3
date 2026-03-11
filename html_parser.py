#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parser de HTML de Apólices Paramétricas
========================================
Extrai parâmetros de regulação de arquivos HTML gerados pelo sistema R/Shiny
com suporte à estrutura do CHIRPS V3.

Autor: Sistema Paramétrico V3 - dagrofic
Versão: 3.0.0
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================================
# PARSER PRINCIPAL
# ============================================================================

def parse_html_content(html_content: str) -> dict:
    """
    Extrai todos os parâmetros de regulação de uma apólice HTML.
    
    Suporta os formatos:
    - "Parametric Rain Cover" (CHIRPS)
    - "Parametric Temperature Cover" (AgERA5)
    
    Returns:
        dict com chaves:
            data_provider, type_of_cover, period_start, period_end,
            latitude, longitude, strike, exit_point, limit, tick,
            deductible_pct, insured, policy_date, roi, coord_source
    """
    result = {}

    # ─── Tipo de Cobertura ─────────────────────────────────────────────────
    result.update(_extract_cover_type(html_content))

    # ─── Segurado ──────────────────────────────────────────────────────────
    insured_match = re.search(r'[Ii]nsured\s*:\s*([^\n<]+)', html_content)
    if insured_match:
        result["insured"] = insured_match.group(1).strip()

    # ─── Data do documento ─────────────────────────────────────────────────
    date_match = re.search(r'Date\s*:\s*(\d{4}-\d{2}-\d{2})', html_content)
    if date_match:
        result["policy_date"] = date_match.group(1)

    # ─── Período ───────────────────────────────────────────────────────────
    result.update(_extract_period(html_content))

    # ─── Coordenadas ───────────────────────────────────────────────────────
    result.update(_extract_coordinates(html_content))

    # ─── Parâmetros Financeiros ────────────────────────────────────────────
    result.update(_extract_financial_params(html_content))

    # ─── Taxa ──────────────────────────────────────────────────────────────
    roi_match = re.search(r'(?:ROL|Rate\s+On\s+Limit)\s*[:\)]\s*([\d.]+)%', html_content, re.IGNORECASE)
    if roi_match:
        result["roi"] = float(roi_match.group(1))

    rate_match = re.search(r'Indicative\s+Rate[^:]*:\s*([\d.]+)%', html_content, re.IGNORECASE)
    if rate_match:
        result["indicative_rate"] = float(rate_match.group(1))

    # ─── Franquia ──────────────────────────────────────────────────────────
    ded_match = re.search(r'[Dd]eductible\s*:\s*([\d.]+)\s*%', html_content)
    if ded_match:
        result["deductible_pct"] = float(ded_match.group(1))
    else:
        result["deductible_pct"] = 0.0

    logger.info(f"Parâmetros extraídos: {result}")
    return result


# ============================================================================
# FUNÇÕES AUXILIARES DE EXTRAÇÃO
# ============================================================================

def _extract_cover_type(html: str) -> dict:
    """Detecta tipo de cobertura (precipitação vs temperatura)"""
    html_upper = html.upper()

    # CHIRPS → precipitação
    if "CHIRPS" in html_upper:
        return {
            "data_provider": "CHIRPS V3.0",
            "type_of_cover": "precipitation",
            "cover_description": "Déficit de Precipitação"
        }

    # AgERA5 / ERA5 → temperatura
    if "AGERA5" in html_upper or "ERA5" in html_upper:
        return {
            "data_provider": "AgERA5",
            "type_of_cover": "temperature",
            "cover_description": "Temperatura Mínima"
        }

    # Inferência por contexto
    if any(kw in html.lower() for kw in ["precipit", "chuva", "rainfall", "rain cover"]):
        return {
            "data_provider": "CHIRPS V3.0",
            "type_of_cover": "precipitation",
            "cover_description": "Déficit de Precipitação"
        }

    if any(kw in html.lower() for kw in ["temperat", "frio", "geada", "frost"]):
        return {
            "data_provider": "AgERA5",
            "type_of_cover": "temperature",
            "cover_description": "Temperatura Mínima"
        }

    return {
        "data_provider": "CHIRPS V3.0",
        "type_of_cover": "precipitation",
        "cover_description": "Déficit de Precipitação"
    }


def _extract_period(html: str) -> dict:
    """Extrai período de cobertura"""
    result = {}

    # Padrão principal: "Period cover : From : YYYY-MM-DD to : YYYY-MM-DD"
    patterns = [
        r'Period\s*cover\s*:\s*From\s*:\s*(\d{4}-\d{2}-\d{2})\s*to\s*:\s*(\d{4}-\d{2}-\d{2})',
        r'Period\s*[Cc]over[:\s]*(\d{4}-\d{2}-\d{2})\s*(?:to|até|a|-)\s*(\d{4}-\d{2}-\d{2})',
        r'Vigência\s*do\s*Seguro.*?(\d{2}/\d{2}/\d{4}).*?(\d{2}/\d{2}/\d{4})',
    ]

    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            start_raw, end_raw = m.group(1), m.group(2)
            # Normalizar formato DD/MM/YYYY se necessário
            if "/" in start_raw:
                start_raw = _convert_date_format(start_raw)
                end_raw = _convert_date_format(end_raw)
            result["period_start"] = start_raw
            result["period_end"] = end_raw
            return result

    # Fallback: encontrar datas ISO no documento
    dates = re.findall(r'(\d{4}-\d{2}-\d{2})', html)
    valid_dates = [d for d in dates if "2024" <= d[:4] <= "2030"]
    if len(valid_dates) >= 2:
        result["period_start"] = valid_dates[0]
        result["period_end"] = valid_dates[1]

    return result


def _convert_date_format(date_str: str) -> str:
    """Converte DD/MM/YYYY para YYYY-MM-DD"""
    parts = date_str.split("/")
    if len(parts) == 3:
        return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return date_str


def _extract_coordinates(html: str) -> dict:
    """
    Extrai coordenadas da apólice HTML.
    Prioriza chirps_lat/chirps_lon do JSON da tabela de clustering R.
    """
    result = {}

    # ─── Padrão 1: JSON DataTable com chirps_lat, chirps_lon ───────────────
    # Formato: "data":[[...],[-28.xxx],[-50.xxx]]} container:..chirps_lat..chirps_lon
    # Identifica pelo container que menciona chirps_lat e chirps_lon nas colunas
    chirps_table_pattern = r'"data":\[\[.*?\],\[([-\d.]+)\],\[([-\d.]+)\]\].*?chirps_lat.*?chirps_lon'
    m = re.search(chirps_table_pattern, html, re.DOTALL)
    if m:
        lat_val = float(m.group(1))
        lon_val = float(m.group(2))
        if _is_valid_brazil_coord(lat_val, lon_val):
            result["latitude"] = lat_val
            result["longitude"] = lon_val
            result["coord_source"] = "chirps_table_json"
            return result

    # ─── Padrão 2: JSON DataTable simples ──────────────────────────────────
    # "data":[[id],[cluster],[lat],[lon],[area],[weight],[id],[chirps_lat],[chirps_lon]]
    # Os últimos dois valores são chirps_lat e chirps_lon
    data_pattern = r'"data":\[\[.*?\],\[([-\d.]+)\],\[([-\d.]+)\]\]'
    matches = list(re.finditer(data_pattern, html))
    for m in reversed(matches):  # Prioriza o último match (mais específico)
        lat_val = float(m.group(1))
        lon_val = float(m.group(2))
        if _is_valid_brazil_coord(lat_val, lon_val):
            result["latitude"] = lat_val
            result["longitude"] = lon_val
            result["coord_source"] = "data_table_json"
            return result

    # ─── Padrão 3: Leaflet setView ─────────────────────────────────────────
    leaflet = re.search(r'setView\(\[([-\d.]+),\s*([-\d.]+)\]', html)
    if leaflet:
        lat_val = float(leaflet.group(1))
        lon_val = float(leaflet.group(2))
        if _is_valid_brazil_coord(lat_val, lon_val):
            result["latitude"] = lat_val
            result["longitude"] = lon_val
            result["coord_source"] = "leaflet_setView"
            return result

    # ─── Padrão 4: Texto explícito Latitude/Longitude ──────────────────────
    lat_m = re.search(r'[Ll]at(?:itude)?\s*[:\s]\s*([-\d.]+)', html)
    lon_m = re.search(r'[Ll]on(?:gitude)?\s*[:\s]\s*([-\d.]+)', html)
    if lat_m and lon_m:
        lat_val = float(lat_m.group(1))
        lon_val = float(lon_m.group(1))
        if _is_valid_brazil_coord(lat_val, lon_val):
            result["latitude"] = lat_val
            result["longitude"] = lon_val
            result["coord_source"] = "text_explicit"
            return result

    # ─── Padrão 5: AgERA_locs para temperatura ─────────────────────────────
    agera_idx = html.find("AgERA_locs_lat")
    if agera_idx > 0:
        # Extrair o bloco JSON ao redor
        start = html.rfind('"data":', 0, agera_idx)
        if start > 0:
            block = html[start:start + 2000]
            float_vals = re.findall(r'\[([-\d.]+)\]', block)
            for i in range(len(float_vals) - 1):
                lat_val = float(float_vals[i])
                lon_val = float(float_vals[i + 1])
                if _is_valid_brazil_coord(lat_val, lon_val):
                    result["latitude"] = lat_val
                    result["longitude"] = lon_val
                    result["coord_source"] = "agera_locs"
                    return result

    logger.warning("Coordenadas não encontradas no HTML")
    return result


def _is_valid_brazil_coord(lat: float, lon: float) -> bool:
    """Valida se coordenadas estão dentro do território brasileiro (com margem)"""
    return (-35.0 <= lat <= 5.0) and (-75.0 <= lon <= -28.0)


def _extract_financial_params(html: str) -> dict:
    """Extrai parâmetros financeiros: Strike, Exit, Limit, Tick"""
    result = {}

    # ─── Strike ────────────────────────────────────────────────────────────
    strike_patterns = [
        r'[Ss]trike\s*[Pp]recipitation\s*:\s*([\d.]+)\s*mm',
        r'[Ss]trike\s*temperature\s*:\s*(-?[\d.]+)\s*°?C?',
        r'[Ss]trike\s*:\s*([\d.]+)\s*mm',
        r'[Ss]trike\s*:\s*(-?[\d.]+)',
    ]
    for pat in strike_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                result["strike"] = val
                break
            except ValueError:
                pass

    # ─── Exit Point ────────────────────────────────────────────────────────
    exit_patterns = [
        r'[Ee]xit\s*[Pp]recipitation\s*:\s*([\d.]+)\s*mm',
        r'[Ee]xit\s*temperature\s*:\s*(-?[\d.]+)\s*°?C?',
        r'[Ee]xit\s*[Pp]oint\s*:\s*(-?[\d.]+)',
        r'[Ee]xit\s*:\s*(-?[\d.]+)\s*(?:mm|°C)?',
        r'[Ee]xit\s*:(-?[\d.]+)',
    ]
    for pat in exit_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1))
                result["exit_point"] = val
                break
            except ValueError:
                pass
    if "exit_point" not in result:
        result["exit_point"] = 0.0

    # ─── Limit ─────────────────────────────────────────────────────────────
    limit_patterns = [
        r'[Ll]imit\s+of\s+[Ii]ndemnity\s*[:\s]*([\d,]+\.?\d*)',
        r'[Ll]imit\s*[:\s]*([\d,]+\.?\d*)',
    ]
    for pat in limit_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    result["limit"] = val
                    break
            except ValueError:
                pass

    # ─── Tick ──────────────────────────────────────────────────────────────
    tick_patterns = [
        r'[Tt]ick\s*[:\s]*([\d,]+\.?\d*)',
        r'[Tt]ick\s*per\s*mm\s*[:\s]*([\d,]+\.?\d*)',
    ]
    for pat in tick_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    result["tick"] = val
                    break
            except ValueError:
                pass

    return result


# ============================================================================
# CÁLCULO DE SINISTRO
# ============================================================================

def calculate_parametric_claim(
    total_value: float,
    type_of_cover: str,
    strike: float,
    exit_point: float = 0.0,
    limit: float = 0.0,
    tick: float = 0.0,
    deductible_pct: float = 0.0
) -> dict:
    """
    Calcula resultado do sinistro paramétrico.
    
    Para precipitação: sinistro se total < strike (déficit de chuva)
    Para temperatura: sinistro se mínimo < strike (geada)
    
    Args:
        total_value: Precipitação total ou temperatura mínima observada
        type_of_cover: 'precipitation' ou 'temperature'
        strike: Valor de gatilho
        exit_point: Ponto de saída (máximo possível)
        limit: Limite máximo de indenização (BRL)
        tick: Valor por unidade (BRL/mm ou BRL/°C)
        deductible_pct: Franquia em percentual do limit
    
    Returns:
        dict com: triggered, deficit, payout_gross, deductible_value, payout_final, 
                  coverage_pct, message
    """
    triggered = False
    deficit = 0.0
    payout_gross = 0.0
    deductible_value = 0.0
    payout_final = 0.0

    if type_of_cover == "precipitation":
        # Chuva: sinistro se precipitação < strike (seca)
        if total_value < strike:
            triggered = True
            deficit = strike - total_value
            # Limitar déficit ao exit point (strike - exit = range máximo)
            max_deficit = strike - exit_point if exit_point < strike else deficit
            deficit_capped = min(deficit, max_deficit)
            payout_gross = deficit_capped * tick if tick > 0 else 0.0
    else:
        # Temperatura: sinistro se mínimo < strike (geada)
        if total_value < strike:
            triggered = True
            deficit = strike - total_value
            max_deficit = strike - exit_point if exit_point < strike else deficit
            deficit_capped = min(deficit, max_deficit)
            payout_gross = deficit_capped * tick if tick > 0 else 0.0

    if triggered and payout_gross > 0 and limit > 0:
        # Aplicar limit
        payout_limitado = min(payout_gross, limit)
        # Calcular franquia sobre o limit
        deductible_value = limit * (deductible_pct / 100)
        payout_final = max(0.0, payout_limitado - deductible_value)

        # Percentual da cobertura acionada
        coverage_pct = (payout_final / limit * 100) if limit > 0 else 0.0
    else:
        coverage_pct = 0.0

    if triggered:
        msg = f"✅ SINISTRO ACIONADO - Déficit: {deficit:.2f} | Indenização: R$ {payout_final:,.2f}"
    else:
        surplus = total_value - strike
        msg = f"❌ SEM SINISTRO - Excedente: {surplus:.2f} acima do Strike"

    return {
        "triggered": triggered,
        "total_observed": round(total_value, 4),
        "strike": strike,
        "exit_point": exit_point,
        "deficit": round(deficit, 4),
        "payout_gross": round(payout_gross, 2),
        "deductible_value": round(deductible_value, 2),
        "payout_final": round(payout_final, 2),
        "coverage_pct": round(coverage_pct, 2),
        "message": msg
    }
