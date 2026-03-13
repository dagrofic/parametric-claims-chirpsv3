# Documentação Técnica Completa — CHIRPS V3.0 Sistema de Regulação de Sinistros Paramétricos

**Versão:** 3.0.0  
**Autor:** dagrofic / INVESTPREV SEGURADORA SA  
**Data:** 2025-03-13  
**Repositório:** https://github.com/dagrofic/parametric-claims-chirpsv3  

---

## Índice

1. [Visão Geral do Sistema](#1-visão-geral-do-sistema)
2. [Arquitetura Técnica](#2-arquitetura-técnica)
3. [Fonte de Dados CHIRPS V3.0](#3-fonte-de-dados-chirps-v30)
4. [Fluxo Completo de Processamento](#4-fluxo-completo-de-processamento)
5. [Parser HTML de Apólices](#5-parser-html-de-apólices)
6. [Extrator CHIRPS V3 — chirps_v3_extractor.py](#6-extrator-chirps-v3--chirps_v3_extractorpy)
7. [Correção Crítica: floor() vs round() na Seleção de Pixel](#7-correção-crítica-floor-vs-round-na-seleção-de-pixel)
8. [API Flask — app.py](#8-api-flask--apppy)
9. [Cálculo de Sinistro Paramétrico](#9-cálculo-de-sinistro-paramétrico)
10. [Exportação para Excel](#10-exportação-para-excel)
11. [Atualização Automática de Dados](#11-atualização-automática-de-dados)
12. [Validação e Resultados — Todos os Casos](#12-validação-e-resultados--todos-os-casos)
13. [Casos Validados — Detalhes Completos](#13-casos-validados--detalhes-completos)
14. [Deploy e Infraestrutura](#14-deploy-e-infraestrutura)
15. [Endpoints da API](#15-endpoints-da-api)
16. [Estrutura de Arquivos do Projeto](#16-estrutura-de-arquivos-do-projeto)
17. [Dependências Python](#17-dependências-python)
18. [Histórico de Correções e Bugs Resolvidos](#18-histórico-de-correções-e-bugs-resolvidos)

---

## 1. Visão Geral do Sistema

O sistema processa **regulação de sinistros paramétricos** para seguros agrícolas utilizando dados de precipitação **CHIRPS V3.0** (Climate Hazards Group InfraRed Precipitation with Stations, versão 3.0) fornecidos pelo CHC-UCSB (Climate Hazards Center, University of California Santa Barbara).

### O que faz:
1. Recebe o HTML gerado pelo sistema R/Shiny de cotação de apólices
2. Extrai automaticamente: coordenadas GPS exatas, período de cobertura, parâmetros financeiros (Strike, Exit Point, Limit, Tick, Franquia)
3. Localiza e extrai precipitação diária do arquivo NetCDF CHIRPS V3.0 para as coordenadas da apólice
4. Calcula déficit de precipitação e indenização paramétrica
5. Emite relatório Excel com dados diários, auditoria de arquivos e lacunas

### Por que CHIRPS V3.0 (vs V2):
| Característica | CHIRPS V2 | CHIRPS V3.0 |
|---|---|---|
| Latência de dados | 2-3 dias | ✅ 1-2 dias |
| Algoritmo | Original | ✅ Melhorado com correções gauge-adjusted |
| Fonte local | ❌ Google Earth Engine (API key necessária) | ✅ NetCDF local (sem dependência de API) |
| Disponibilidade | Depende do GEE | ✅ 100% autônomo |
| Formato | GEE raster | ✅ NetCDF padrão UCSB |
| Resolução espacial | 0.05° (~5.5 km) | 0.05° (~5.5 km) |
| Cobertura | Global | Global |

---

## 2. Arquitetura Técnica

```
┌─────────────────────────────────────────────────────────────────┐
│                    USUÁRIO / CLIENTE                             │
│              (cola HTML da apólice no sistema)                   │
└─────────────────────────┬───────────────────────────────────────┘
                          │ HTML da apólice
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 INTERFACE WEB (Flask)                            │
│                     app.py                                      │
│  POST /api/process ← HTML                                       │
│  GET  /api/data/status                                          │
│  POST /api/data/download                                        │
│  POST /api/download-excel                                       │
└─────────┬──────────────────────────┬────────────────────────────┘
          │                          │
          ▼                          ▼
┌─────────────────────┐    ┌──────────────────────────────────────┐
│   html_parser.py    │    │       chirps_v3_extractor.py         │
│                     │    │                                      │
│ parse_html_content()│    │ extract_chirps_v3_with_tif_fallback()│
│ - coordenadas GPS   │    │ - Lê NetCDF anual (byYear)           │
│ - período cobertura │    │ - Lê TIFs diários (fallback)         │
│ - Strike/Exit/Limit │    │ - Seleção de pixel: floor()          │
│ - Tick / Franquia   │    │ - Cálculo Haversine distância        │
│                     │    │ - Detecção de lacunas                │
│ calculate_          │    │ - Export Excel                       │
│ parametric_claim()  │    │                                      │
└─────────────────────┘    └──────────────────────────────────────┘
                                        │
                          ┌─────────────▼────────────────────────┐
                          │          FONTES DE DADOS             │
                          │                                      │
                          │  1. NetCDF anual (principal):        │
                          │  data/chirps_v3/{ano}/               │
                          │  chirps-v3.0.rnl.{ano}.days_p05.nc  │
                          │  Fonte: CHC-UCSB (~300-500 MB/ano)   │
                          │                                      │
                          │  2. TIFs diários finais (fallback):  │
                          │  data/chirps_v3/tifs/{mes}{ano}/     │
                          │  chirps-v3.0.rnl.{ano}.{mm}.{dd}.tif│
                          │  ~17 MB/arquivo                      │
                          │                                      │
                          │  NOTA: Dados prelim/sat NUNCA        │
                          │  usados no cálculo de sinistro       │
                          └──────────────────────────────────────┘
```

---

## 3. Fonte de Dados CHIRPS V3.0

### URLs Oficiais

**NetCDF Anuais (byYear) — FONTE PRINCIPAL:**
```
https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/byYear/
Padrão de arquivo: chirps-v3.0.rnl.{ANO}.days_p05.nc
Exemplo 2025: chirps-v3.0.rnl.2025.days_p05.nc
Exemplo 2026: chirps-v3.0.rnl.2026.days_p05.nc
```

**TIFs Diários Finais (rnl) — FALLBACK para meses recentes:**
```
https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/{ANO}/
Padrão: chirps-v3.0.rnl.{ANO}.{MM}.{DD}.tif
Exemplo: chirps-v3.0.rnl.2026.03.01.tif
```

**TIFs Diários Preliminares (prelim/sat) — NUNCA utilizados:**
```
https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/prelim/sat/{ANO}/
Padrão: chirps-v3.0.prelim.{ANO}.{MM}.{DD}.tif
IMPORTANTE: Dados preliminares são ignorados pelo sistema.
Apenas dados finais gauge-adjusted (rnl) são usados no cálculo.
```

### Características Técnicas do Raster
- **Resolução:** 0.05° × 0.05° (aproximadamente 5.5 km no equador)
- **Sistema de Coordenadas:** WGS84 / EPSG:4326
- **Amplitude Latitude:** -60° a +60°
- **Amplitude Longitude:** -180° a +180°
- **Variável principal:** `precip` (mm/dia)
- **Valor nodata:** -9999 (tratado como 0)
- **Transform (TIF):** c=-180.0°, a=0.05°, f=60.0°, e=-0.05°

### Calendário de Disponibilidade de Dados
- **Dados finais (rnl):** Disponíveis com ~1-2 meses de atraso
- **NetCDF anual 2025:** Disponível a partir de ~fevereiro 2026
- **NetCDF anual 2026:** Disponível a partir de ~fevereiro 2027
- **TIFs mensais finais:** Disponíveis mês a mês com ~30 dias de atraso
- **Atualização automática:** Todo dia 15 via GitHub Actions

---

## 4. Fluxo Completo de Processamento

### Passo a Passo Detalhado

```
ENTRADA: HTML da apólice (gerado pelo sistema R/Shiny)
         └── Contém: coordenadas GPS, período, parâmetros contratuais

PASSO 1: parse_html_content(html)
  ├── Detectar tipo de cobertura (CHIRPS = precipitação)
  ├── Extrair segurado (insured)
  ├── Extrair data da apólice
  ├── Extrair período: period_start, period_end
  ├── Extrair coordenadas GPS (4 métodos, em ordem de prioridade):
  │   1. chirps_table_json: JSON DataTable com chirps_lat/chirps_lon
  │   2. data_table_json: JSON DataTable genérico
  │   3. leaflet_setView: Mapa Leaflet setView([lat, lon])
  │   4. text_explicit: Texto "Latitude: X, Longitude: Y"
  └── Extrair parâmetros financeiros: Strike, Exit, Limit, Tick, Franquia

PASSO 2: find_chirps_files_for_period(DATA_DIR, period_start, period_end)
  ├── Calcular anos necessários (ex: 2025, 2026)
  ├── Para cada ano:
  │   ├── Verificar NetCDF anual: data/chirps_v3/{ano}/chirps-v3.0.rnl.{ano}.days_p05.nc
  │   └── Se não existir, verificar arquivos mensais
  └── Retornar lista de caminhos absolutos

PASSO 3: extract_chirps_v3_with_tif_fallback(files, lat, lon, start, end)
  │
  ├── PARTE 1: NetCDF anuais (fonte primária)
  │   └── extract_chirps_v3(files, lat, lon, start, end)
  │       ├── Para cada arquivo NetCDF:
  │       │   ├── open_nc(path) [com fallback h5netcdf → netcdf4 → scipy]
  │       │   ├── detect_coord_names(ds) → lat_name, lon_name, time_name
  │       │   ├── detect_var_name(ds) → "precip"
  │       │   ├── adjust_lon_if_needed() [converte 0-360 para -180/+180 se necessário]
  │       │   ├── ds[var].sel(method="nearest") → pixel mais próximo
  │       │   ├── slice(start, end) → período contratual
  │       │   └── Calcular distância Haversine ponto↔pixel
  │       └── Consolidar DataFrames
  │
  ├── PARTE 2: TIFs diários finais (fallback para datas não cobertas)
  │   └── Para cada dia do período não coberto pelo NetCDF:
  │       ├── find_tif_for_date(ano, mês, dia)
  │       │   ├── Verificar TIF final local: data/chirps_v3/tifs/{mes}{ano}/
  │       │   ├── Verificar TIF prelim local
  │       │   └── AUTO-DOWNLOAD: baixar de CHC-UCSB se não disponível
  │       ├── SE TIF final (rnl) encontrado:
  │       │   └── extract_point_from_tif(tif_path, lat, lon, data)
  │       │       ├── Calcular col_float = (lon - transform.c) / transform.a
  │       │       ├── Calcular row_float = (lat - transform.f) / transform.e
  │       │       ├── col = math.floor(col_float)  ← CRÍTICO: floor, não round!
  │       │       ├── row = math.floor(row_float)  ← CRÍTICO: floor, não round!
  │       │       ├── Clampar para limites do raster
  │       │       ├── Ler valor precip do pixel
  │       │       └── Calcular centroide do pixel e distância Haversine
  │       └── SE TIF preliminar: IGNORADO (lacuna no período)
  │
  └── CONSOLIDAÇÃO:
      ├── Concatenar todos os DataFrames
      ├── Remover duplicatas por data
      ├── Ordenar cronologicamente
      ├── Tratar valores negativos/NaN → 0
      ├── Detectar lacunas no período
      ├── Calcular total_precip = sum(precip)
      └── Definir status: ok / partial / partial_critical / aguardando_dados_finais

PASSO 4: calculate_parametric_claim(total_precip, strike, exit, limit, tick, franquia)
  ├── triggered = total_precip < strike
  ├── deficit = strike - total_precip (se triggered)
  ├── deficit_capped = min(deficit, strike - exit_point)
  ├── payout_gross = deficit_capped × tick
  ├── payout_limitado = min(payout_gross, limit)
  ├── deductible_value = limit × (franquia / 100)
  └── payout_final = max(0, payout_limitado - deductible_value)

SAÍDA:
  ├── JSON completo com:
  │   ├── success, params (todos os parâmetros extraídos)
  │   ├── latitude, longitude (coordenadas contratuais exatas do HTML)
  │   ├── pixel_latitude, pixel_longitude (centroide do pixel CHIRPS usado)
  │   ├── daily_data (array: date, precip, pixel_lat, pixel_lon, distance_km)
  │   ├── total_precip (soma de precipitação no período)
  │   ├── missing_days (dias sem dados)
  │   ├── data_status (ok/partial/partial_critical/aguardando_dados_finais)
  │   ├── claim (triggered, deficit, payout_gross, deductible_value, payout_final)
  │   ├── audit (auditoria por arquivo de dados)
  │   ├── files_used (nomes dos arquivos usados)
  │   └── chirps_version: "V3.0"
  └── Excel (3 abas + resumo):
      ├── dados: séries temporais diárias com pixel coords
      ├── auditoria_arquivos: qual arquivo cobriu qual período
      ├── auditoria_lacunas: dias sem dados
      └── resumo_parametrico: parâmetros + resultado do sinistro
```

---

## 5. Parser HTML de Apólices

**Arquivo:** `html_parser.py`

### Função Principal: `parse_html_content(html)`

Extrai todos os parâmetros da apólice de um documento HTML gerado pelo sistema R/Shiny.

#### Extração de Coordenadas — 4 Métodos em Ordem de Prioridade

**Método 1: chirps_table_json (padrão atual, máxima precisão)**
```python
# Regex: identifica JSON DataTable com chirps_lat e chirps_lon nas colunas
chirps_table_pattern = r'"data":\[\[.*?\],\[([-\d.]+)\],\[([-\d.]+)\]\].*?chirps_lat.*?chirps_lon'
```
- Extrai coordenadas com **precisão máxima** (12+ casas decimais)
- Exemplo: lat=-28.44078166594957, lon=-54.82762756624246
- Fonte: JSON DataTable embutido no HTML pelo R/Shiny com as colunas `chirps_lat` e `chirps_lon`
- Estas coordenadas são calculadas pelo algoritmo de clustering do sistema R que associa cada fazenda ao pixel CHIRPS mais representativo

**Método 2: data_table_json**
```python
data_pattern = r'"data":\[\[.*?\],\[([-\d.]+)\],\[([-\d.]+)\]\]'
```
- Fallback para DataTable genérico
- Usa o último match encontrado (mais específico)

**Método 3: leaflet_setView**
```python
leaflet = re.search(r'setView\(\[([-\d.]+),\s*([-\d.]+)\]', html)
```
- Extrai do mapa interativo Leaflet embutido

**Método 4: text_explicit**
```python
lat_m = re.search(r'[Ll]at(?:itude)?\s*[:\s]\s*([-\d.]+)', html)
lon_m = re.search(r'[Ll]on(?:gitude)?\s*[:\s]\s*([-\d.]+)', html)
```
- Fallback para texto explícito

#### Validação de Coordenadas
```python
def _is_valid_brazil_coord(lat: float, lon: float) -> bool:
    return (-35.0 <= lat <= 5.0) and (-75.0 <= lon <= -28.0)
```
Coordenadas fora deste intervalo são descartadas (não correspondem ao Brasil).

#### Extração de Período
```python
# Padrão principal
r'Period\s*cover\s*:\s*From\s*:\s*(\d{4}-\d{2}-\d{2})\s*to\s*:\s*(\d{4}-\d{2}-\d{2})'
```

#### Extração de Parâmetros Financeiros

| Parâmetro | Padrão | Exemplo |
|---|---|---|
| Strike | `Strike Precipitation : 320 mm` | 320.0 mm |
| Exit Point | `Exit Precipitation : 0 mm` | 0.0 mm |
| Limit | `Limit : 8,388,608` | 8388608.0 BRL |
| Tick | `Tick : 3` | 3.0 BRL/mm |
| Franquia | `Deductible : 0%` | 0.0 % |

### Função: `calculate_parametric_claim()`

```python
def calculate_parametric_claim(
    total_value: float,   # Precipitação total observada (mm)
    type_of_cover: str,   # 'precipitation' ou 'temperature'
    strike: float,        # Strike (mm)
    exit_point: float,    # Exit Point (mm) — limite inferior
    limit: float,         # Limite máximo (BRL)
    tick: float,          # Tick (BRL/mm)
    deductible_pct: float # Franquia (% do limit)
) -> dict
```

**Lógica de cálculo (precipitação):**
```
SE total_precip < strike:
    triggered = True
    deficit = strike - total_precip
    deficit_capped = min(deficit, strike - exit_point)
    payout_gross = deficit_capped × tick
    payout_limitado = min(payout_gross, limit)
    deductible_value = limit × (deductible_pct / 100)
    payout_final = max(0, payout_limitado - deductible_value)
```

---

## 6. Extrator CHIRPS V3 — chirps_v3_extractor.py

### Hierarquia de Fontes de Dados

```
PRIORIDADE 1: NetCDF anual byYear (dados finais completos)
  └── data/chirps_v3/{ano}/chirps-v3.0.rnl.{ano}.days_p05.nc
  └── Tamanho: ~300-500 MB por ano
  └── Cobertura: 365/366 dias do ano completo
  └── Disponibilidade: ~30 dias após fim do ano

PRIORIDADE 2: TIFs diários finais rnl (meses recentes sem byYear)
  └── data/chirps_v3/tifs/{mes}{ano}/chirps-v3.0.rnl.{ano}.{mm}.{dd}.tif
  └── Tamanho: ~17 MB por arquivo
  └── Cobertura: 1 dia por arquivo
  └── Disponibilidade: ~30 dias após o dia da medição

NUNCA USADO: TIFs diários preliminares (prelim/sat)
  └── Dados não gauge-adjusted → imprecisos para regulação
  └── Sistema detecta mas IGNORA; registra como lacuna
```

### Funções Principais

#### `extract_chirps_v3_with_tif_fallback()` — Função Recomendada

```python
def extract_chirps_v3_with_tif_fallback(
    files: list,           # Arquivos NetCDF encontrados para o período
    target_lat: float,     # Latitude contratual (exata do HTML)
    target_lon: float,     # Longitude contratual (exata do HTML)
    required_start: str,   # Data início YYYY-MM-DD
    required_end: str,     # Data fim YYYY-MM-DD
    data_dir: str,         # Diretório base dos dados
    tif_base_dir: str,     # Diretório base dos TIFs
    use_policy_nc: bool    # Usar NetCDF de apólice se disponível
) -> dict
```

**Retorno:**
```python
{
    "df": DataFrame,            # Dados diários completos
    "audit_df": DataFrame,      # Auditoria por arquivo
    "gaps_df": DataFrame,       # Dias sem dados
    "total_precip": float,      # Precipitação total (mm)
    "missing_days": int,        # Dias sem dados
    "status": str,              # ok/partial/partial_critical/aguardando_dados_finais
    "message": str              # Descrição do resultado
}
```

#### `extract_point_from_nc()` — Extração do NetCDF

```python
# Usa método "nearest" do xarray para pixel mais próximo
da = ds[var_name].sel(
    {lat_name: target_lat, lon_name: lon_adj},
    method="nearest"
).sel({time_name: slice(required_start, required_end)})
```

#### `extract_point_from_tif()` — Extração do TIF

```python
# Seleção do pixel usando floor() — CORREÇÃO CRÍTICA
col_float = (target_lon - src.transform.c) / src.transform.a
row_float = (target_lat - src.transform.f) / src.transform.e
col = math.floor(col_float)  # ← NÃO round()!
row = math.floor(row_float)  # ← NÃO round()!
```

---

## 7. Correção Crítica: floor() vs round() na Seleção de Pixel

### O Bug

A função original `extract_point_from_tif` usava `rowcol(transform, lon, lat, op=round)` do rasterio, que internamente aplica `round()` do Python para selecionar o índice do pixel.

**Exemplo do erro:**
```
Coordenada: lon = -54.8183
Transform: c = -180.0, a = 0.05 (resolução)

col_float = (-54.8183 - (-180.0)) / 0.05 = 125.1817 / 0.05 = 2503.634

round(2503.634) = 2504  ← ERRADO (Python banker's rounding)
floor(2503.634) = 2503  ← CORRETO
```

**Por que round() dá o resultado errado:**

O arredondamento padrão seleciona o pixel cujo **centroide** está mais próximo. Mas CHIRPS V3 define o pixel como o quadrado:
```
Pixel 2503: longitude [-54.85, -54.80)  ← centroide: -54.825
Pixel 2504: longitude [-54.80, -54.75)  ← centroide: -54.775
```

A coordenada -54.8183 está **dentro do pixel 2503** (entre -54.85 e -54.80), mas `round(2503.634)` seleciona o pixel 2504 porque a fração .634 > 0.5.

**Resultado prático:**
```
lon = -54.8183, round → pixel (-28.4750, -54.7750), precipip = 7.02 mm  ← ERRADO
lon = -54.8183, floor → pixel (-28.4750, -54.8250), precip = 8.61 mm    ← CORRETO
```

### A Correção

```python
# ANTES (bugado):
row, col = rasterio.transform.rowcol(src.transform, target_lon, target_lat, op=round)

# DEPOIS (correto):
col_float = (target_lon - src.transform.c) / src.transform.a
row_float = (target_lat - src.transform.f) / src.transform.e
col = math.floor(col_float)
row = math.floor(row_float)
```

### Impacto na Validação

| Caso | Coordenada | Antes (round) | Depois (floor) | Referência | Status |
|---|---|---|---|---|---|
| Fábio 321 | (-28.4573, -54.8183) | 219.84 mm (dez) | 226.91 mm | 226.91 mm | ✅ |
| Fábio 322 | (-28.4408, -54.8276) | 226.91 mm (dez) | 248.71 mm | 248.71 mm | ✅ |
| Oneide 325 | (-28.4388, -55.1922) | 246.41 mm (dez) | 237.13 mm | 237.13 mm | ✅ |

---

## 8. API Flask — app.py

### Inicialização
```python
app = Flask(__name__)
DATA_DIR = os.environ.get("CHIRPS_DATA_DIR", "./data/chirps_v3")
```

### Endpoint Principal: `POST /api/process`

**Input (JSON):**
```json
{
    "html": "<html>...conteúdo completo da apólice HTML...</html>"
}
```

**Output (JSON) — sucesso:**
```json
{
    "success": true,
    "params": {
        "data_provider": "CHIRPS V3.0",
        "type_of_cover": "precipitation",
        "cover_description": "Déficit de Precipitação",
        "insured": "KOVR Dual",
        "policy_date": "2025-11-12",
        "period_start": "2025-12-15",
        "period_end": "2026-03-31",
        "latitude": -28.457271546993,
        "longitude": -54.8183084494764,
        "coord_source": "chirps_table_json",
        "strike": 320.0,
        "exit_point": 0.0,
        "limit": 8388608.0,
        "tick": 3.0,
        "deductible_pct": 0.0
    },
    "latitude": -28.457271546993,
    "longitude": -54.8183084494764,
    "pixel_latitude": -28.475,
    "pixel_longitude": -54.825,
    "daily_data": [
        {"date": "2025-12-15", "precip": 7.0171, "pixel_lat": -28.475, "pixel_lon": -54.825, "distance_km": 2.5},
        ...
    ],
    "total_precip": 285.4331,
    "missing_days": 59,
    "data_status": "partial_critical",
    "claim": {
        "triggered": true,
        "total_observed": 285.4331,
        "strike": 320.0,
        "deficit": 34.5669,
        "payout_gross": 103.7,
        "deductible_value": 0.0,
        "payout_final": 103.7,
        "coverage_pct": 0.0,
        "message": "✅ SINISTRO ACIONADO - Déficit: 34.57 | Indenização: R$ 103.70"
    },
    "audit": [...],
    "files_used": ["chirps-v3.0.rnl.2025.days_p05.nc"],
    "chirps_version": "V3.0",
    "source_url": "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/byYear/"
}
```

---

## 9. Cálculo de Sinistro Paramétrico

### Fórmula Completa

```
Variáveis:
  P = Precipitação total observada no período (mm)
  S = Strike (mm) — gatilho do sinistro
  E = Exit Point (mm) — piso mínimo de precipitação
  L = Limit (BRL) — indenização máxima
  T = Tick (BRL/mm) — valor por milímetro de déficit
  F = Franquia (% do Limit)

Cálculo:
  1. triggered = (P < S)
  
  2. deficit = max(0, S - P)          [mm de déficit]
  
  3. max_deficit = S - E              [máximo possível]
     deficit_capped = min(deficit, max_deficit)
  
  4. payout_gross = deficit_capped × T   [indenização bruta, BRL]
  
  5. payout_limitado = min(payout_gross, L)
  
  6. deductible_value = L × (F / 100)   [valor da franquia, BRL]
  
  7. payout_final = max(0, payout_limitado - deductible_value)
```

### Exemplo Real — Fábio Fernandes 322 (apólice 1000100000322)

```
Período: 2025-12-15 a 2026-03-31
Coordenadas: (-28.4408, -54.8276)
Pixel CHIRPS: (-28.4250, -54.8250)

P = 310.9997 mm  (total até 31/jan + TIFs dez; fev-mar/26 pendentes)
S = 320.0 mm
E = 0.0 mm
L = 8,388,608 BRL
T = 3.0 BRL/mm
F = 0%

triggered = (310.9997 < 320.0) = True
deficit = 320.0 - 310.9997 = 9.0003 mm
payout_gross = 9.0003 × 3.0 = 27.0009 BRL ≈ 27.00 BRL
payout_final = 27.00 BRL (sem franquia, sem exceder limit)
```

---

## 10. Exportação para Excel

O Excel de regulação contém 4 abas:

### Aba 1: `dados`
| Coluna | Descrição |
|---|---|
| time | Data (YYYY-MM-DD) |
| latitude | Latitude contratual (exata do HTML) |
| longitude | Longitude contratual (exata do HTML) |
| precip | Precipitação diária (mm, 6 casas decimais) |
| pixel_latitude | Latitude do centroide do pixel CHIRPS usado |
| pixel_longitude | Longitude do centroide do pixel CHIRPS usado |
| distance_km | Distância Haversine ponto contratual ↔ centroide pixel |
| source_file | Nome do arquivo NetCDF/TIF de origem |
| **TOTAL** | **Linha de totais no final** |

### Aba 2: `auditoria_arquivos`
Registro de cada arquivo processado: status, variável lida, período coberto, dias extraídos, pixel utilizado.

### Aba 3: `auditoria_lacunas`
Lista de todos os dias sem dados no período contratual.

### Aba 4: `resumo_parametrico`
Resumo completo: parâmetros contratuais + resultado do sinistro (deficit, indenização bruta, franquia, indenização final).

---

## 11. Atualização Automática de Dados

### GitHub Actions — `.github/workflows/update-chirps-data.yml`

**Agendamento:** Todo dia 15 de cada mês às 08:00 UTC (05:00 Brasília)

**Lógica:**
1. Verifica disponibilidade do arquivo anual no CHC-UCSB (HEAD request)
2. Se disponível, aciona `POST /api/data/update` no sistema hospedado no Render
3. Aguarda 60 segundos e verifica status

**Para ativar:**
```
GitHub → Settings → Secrets → Actions
RENDER_APP_URL = https://claimsparametricchirpsv3.onrender.com
```

### Política de Atualização do Arquivo Anual

```python
# Arquivo do ano atual:
# - Se não existe: baixar quando current_day >= 15 ou current_month > 1
# - Se existe: atualizar se o arquivo tem mais de 1 mês de idade E current_day >= 15

# Anos anteriores:
# - Baixar apenas se não existe (dados imutáveis)
```

---

## 12. Validação e Resultados — Todos os Casos

### Tabela de Validação Completa

| Caso | Apólice | Coordenada Contratual | Pixel CHIRPS | Total Calculado | Total Referência | Δ | Status |
|---|---|---|---|---|---|---|---|
| 3,9.html | Fábio 1000100000321 | (-28.457272, -54.818308) | (-28.4750, -54.8250) | 226.91 mm¹ | 226.91 mm | 0.001 | ✅ |
| 3,7.html | Fábio 1000100000322 | (-28.440782, -54.827628) | (-28.4250, -54.8250) | 248.71 mm¹ | 248.71 mm | 0.004 | ✅ |
| 3,8(3).html | Jose Oneide 1000100000325 | (-28.438767, -55.192249) | (-28.4250, -55.1750) | 237.13 mm¹ | 237.13 mm | 0.004 | ✅ |
| 4,3.html | Palmeiras 547 | (-20.2750, -54.6250) | (-20.2750, -54.6250) | 645.79 mm | 645.7899 mm | 0.0002 | ✅ |
| 4,5.html | Palmeiras 548 | (-20.2250, -54.6250) | (-20.2250, -54.6250) | 655.31 mm | 655.3109 mm | 0.0001 | ✅ |
| 4,4.html | Palmeiras 549 | (-20.2250, -54.6250) | (-20.2250, -54.6250) | 591.15 mm | 591.1500 mm | 0.0001 | ✅ |
| 4,1.html | Palmeiras 550 | (-20.2750, -54.6250) | (-20.2750, -54.6250) | 580.08 mm | 580.0818 mm | 0.0000 | ✅ |
| — | Clovis Colombo 113 | (-28.675, -50.325) | (-28.6750, -50.3250) | 320.4261 mm | 320.4261 mm | 0.0000 | ✅ |

¹ Totais de **dez 2025** (17 dias: 15-31/dez); dados jan/2026 = +jan total nos valores completos abaixo.

### Totais Completos (dez/2025 + jan/2026)

| Apólice | Total dez+jan | Sinistro? | Indenização |
|---|---|---|---|
| Fábio 321 (3,9) | 285.4331 mm | ✅ SIM | R$ 103.70 |
| Fábio 322 (3,7) | 310.9997 mm | ✅ SIM | R$ 27.00 |
| Jose Oneide 325 (3,8(3)) | 308.6424 mm | ✅ SIM | R$ 34.07 |
| Cesar 323 (3,8) | 267.55 mm (parcial) | ✅ SIM | R$ 157.34 |
| Cesar/Fábio (3,9(1)) | 274.53 mm (parcial) | ✅ SIM | R$ 136.40 |

*Nota: parcial = 59 dias de fev-mar/2026 ainda não publicados pelo CHC-UCSB em mar/2026*

---

## 13. Casos Validados — Detalhes Completos

### Caso 1: Fábio Fernandes Comparsi — Apólice 1000100000321

```
HTML: 3,9.html
Tipo: CHIRPS V3.0 — Déficit de Precipitação
Segurado: KOVR Dual
Data apólice: 2025-11-12
Período: 2025-12-15 a 2026-03-31 (107 dias)
Coordenada contratual: lat=-28.457271546993, lon=-54.8183084494764
Fonte coordenada: chirps_table_json
Pixel CHIRPS: lat=-28.4750, lon=-54.8250
Distância ponto↔pixel: ~4.67 km

Strike: 320.0 mm
Exit Point: 0.0 mm  
Limit: 8,388,608.0 BRL
Tick: 3.0 BRL/mm
Franquia: 0%

Dados disponíveis: dez/2025 (TIFs) + jan/2026 (NetCDF 2026)
Total observado: 285.4331 mm (48/107 dias com dados)
Dias faltantes: 59 (fev+mar/2026 aguardando publicação CHC-UCSB)
Status: partial_critical

Resultado ATUAL:
  Sinistro acionado: SIM
  Déficit: 34.5669 mm
  Indenização: R$ 103.70

Validação dez/2025 (17 dias):
  Total extraído: 226.9087 mm
  Referência (email 13/fev/2026): 226.91 mm
  Diferença: 0.0013 mm ✅
```

### Caso 2: Fábio Fernandes Comparsi — Apólice 1000100000322

```
HTML: 3,7.html
Tipo: CHIRPS V3.0 — Déficit de Precipitação
Segurado: KOVR Dual
Data apólice: 2025-11-12
Período: 2025-12-15 a 2026-03-31 (107 dias)
Coordenada contratual: lat=-28.44078166594957, lon=-54.82762756624246
Fonte coordenada: chirps_table_json
Pixel CHIRPS: lat=-28.4250, lon=-54.8250
Distância ponto↔pixel: ~2.08 km

Strike: 320.0 mm
Exit Point: 0.0 mm
Limit: 8,388,608.0 BRL
Tick: 3.0 BRL/mm
Franquia: 0%

Total observado: 310.9997 mm (48/107 dias)
Dias faltantes: 59 (fev+mar/2026)
Status: partial_critical

Resultado ATUAL (com dados parciais):
  Sinistro acionado: SIM (310.9997 < 320.0)
  Déficit: 9.0003 mm
  Indenização: R$ 27.00

Validação dez/2025:
  Total extraído: 248.7139 mm
  Referência: 248.71 mm
  Diferença: 0.0039 mm ✅
```

### Caso 3: Jose Oneide Comparsi — Apólice 1000100000325

```
HTML: 3,8(3).html
Tipo: CHIRPS V3.0 — Déficit de Precipitação
Segurado: KOVR Dual
Data apólice: 2025-11-12
Período: 2025-12-15 a 2026-03-31 (107 dias)
Coordenada contratual: lat=-28.4387673243807, lon=-55.19224936349499
Fonte coordenada: chirps_table_json
Pixel CHIRPS: lat=-28.4250, lon=-55.1750
Distância ponto↔pixel: ~2.8 km

Strike: 320.0 mm
Exit Point: 0.0 mm
Limit: 8,388,608.0 BRL
Tick: 3.0 BRL/mm
Franquia: 0%

Total observado: 308.6424 mm (48/107 dias)
Dias faltantes: 59 (fev+mar/2026)
Status: partial_critical

Resultado ATUAL:
  Sinistro acionado: SIM
  Déficit: 11.3576 mm
  Indenização: R$ 34.07

Validação dez/2025:
  Total extraído: 237.1342 mm
  Referência: 237.13 mm
  Diferença: 0.0042 mm ✅
```

### Caso 4: Palmeiras Agro-Pastoril Ltda — Apólice 547

```
HTML: 4,3.html
Tipo: CHIRPS V3.0 — Déficit de Precipitação
Período: 2025-10-15 a 2026-02-15 (124 dias)
Coordenada contratual: lat=-20.2750, lon=-54.6250
Pixel CHIRPS: lat=-20.2750, lon=-54.6250 (coordenada é exatamente o centroide do pixel)

Strike: definido no HTML
Dados: NetCDF 2025 + NetCDF 2026 parcial (15 dias faltantes)
Total: 645.7897 mm vs referência 645.7899 mm (Δ=0.0002 mm) ✅
```

### Caso 5: Palmeiras Agro-Pastoril Ltda — Apólice 548

```
HTML: 4,5.html
Coordenada: lat=-20.2250, lon=-54.6250
Total: 655.3108 mm vs referência 655.3109 mm (Δ=0.0001 mm) ✅
```

### Caso 6: Palmeiras Agro-Pastoril Ltda — Apólice 549

```
HTML: 4,4.html
Período: 2025-11-01 a 2026-02-28
Total: 591.1499 mm vs referência 591.1500 mm (Δ=0.0001 mm) ✅
```

### Caso 7: Palmeiras Agro-Pastoril Ltda — Apólice 550

```
HTML: 4,1.html  
Período: 2025-11-01 a 2026-02-28
Total: 580.0818 mm vs referência 580.0818 mm (Δ=0.0000 mm) ✅
```

### Caso 8: Clovis Colombo — Apólice 113

```
Coordenada: lat=-28.675, lon=-50.325
Pixel CHIRPS: lat=-28.6750, lon=-50.3250 (centroide exato)
Fonte: NetCDF 2025 anual (byYear)
Total: 320.4261 mm vs referência 320.4261 mm (Δ=0.0000 mm) ✅
```

---

## 14. Deploy e Infraestrutura

### Render.com (Hospedagem Principal)

**URL Produção:** https://claimsparametricchirpsv3.onrender.com  
**URL Domínio Customizado:** https://claimsparametricchirpsv3.insuranceandreinsuranceapps.com

**Configuração `render.yaml`:**
```yaml
services:
  - type: web
    name: claimsparametricchirpsv3
    runtime: docker
    dockerfilePath: ./Dockerfile
    region: oregon          # Oregon: mais próximo do servidor CHC-UCSB (California)
    plan: standard          # Necessário para disco persistente
    envVars:
      - key: PORT
        value: 5000
      - key: CHIRPS_DATA_DIR
        value: /data/chirps_v3
      - key: SECRET_KEY
        generateValue: true
    disk:
      name: chirps-v3-data
      mountPath: /data
      sizeGB: 10            # 10 GB para ~15 anos de dados CHIRPS
    healthCheckPath: /
    autoDeploy: true
    branch: main
```

### Docker

**`Dockerfile`:**
```dockerfile
FROM python:3.11-slim

# Dependências do sistema (HDF5/NetCDF)
RUN apt-get install -y libhdf5-dev libnetcdf-dev wget curl

# Instalar dependências Python
COPY requirements.txt .
RUN pip install -r requirements.txt

# Iniciar com Gunicorn (2 workers, timeout 120s)
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 app:app
```

### Cloudflare (DNS e CDN)

**Domínio:** insuranceandreinsuranceapps.com  
**Subdomínio CHIRPS V3:** claimsparametricchirpsv3.insuranceandreinsuranceapps.com  

Configuração DNS (CNAME):
```
claimsparametricchirpsv3 → claimsparametricchirpsv3.onrender.com
```

### GitHub

**Repositório:** https://github.com/dagrofic/parametric-claims-chirpsv3  
**Branch principal:** main  
**Auto-deploy:** Qualquer push na branch main dispara deploy no Render

---

## 15. Endpoints da API

| Método | Endpoint | Descrição | Input | Output |
|---|---|---|---|---|
| `GET` | `/` | Interface principal | — | HTML |
| `GET` | `/admin` | Painel de administração | — | HTML |
| `POST` | `/api/process` | Processar apólice HTML → precipitação + sinistro | `{"html": "..."}` | JSON completo |
| `POST` | `/api/calculate` | Recalcular sinistro com parâmetros customizados | `{"total_precip": X, "strike": Y, ...}` | JSON sinistro |
| `POST` | `/api/download-excel` | Gerar Excel de regulação | `{"html": "...", "daily_data": [...]}` | Arquivo XLSX |
| `GET` | `/api/data/status` | Status dos arquivos CHIRPS V3 locais | — | JSON status |
| `POST` | `/api/data/download` | Iniciar download de arquivo anual | `{"year": 2026}` | `{"task_id": "..."}` |
| `POST` | `/api/data/update` | Verificar e atualizar todos os arquivos | `{"years": [2025, 2026]}` | `{"task_id": "..."}` |
| `GET` | `/api/task/{id}` | Status de tarefa em background | — | JSON status tarefa |

---

## 16. Estrutura de Arquivos do Projeto

```
parametric-claims-chirpsv3/
├── app.py                          # API Flask principal (19.5 KB)
│   ├── /api/process                → Processamento principal
│   ├── /api/calculate              → Recálculo de sinistro
│   ├── /api/download-excel         → Export Excel
│   ├── /api/data/status            → Status arquivos CHIRPS
│   ├── /api/data/download          → Download arquivo anual
│   ├── /api/data/update            → Atualização automática
│   └── /api/task/<id>              → Status tarefas async
│
├── chirps_v3_extractor.py          # Core extrator (47.7 KB)
│   ├── open_nc()                   → Abre NetCDF (h5netcdf/netcdf4/scipy)
│   ├── detect_coord_names()        → Detecta lat/lon/time no dataset
│   ├── detect_var_name()           → Detecta variável de precipitação
│   ├── adjust_lon_if_needed()      → Converte longitude 0-360→-180/+180
│   ├── extract_point_from_nc()     → Extrai ponto do NetCDF
│   ├── extract_point_from_tif()    → Extrai ponto do TIF (com floor())
│   ├── extract_chirps_v3()         → Processa múltiplos NetCDFs
│   ├── extract_chirps_v3_with_tif_fallback() → Função principal completa
│   ├── find_tif_for_date()         → Localiza/baixa TIF para data
│   ├── _download_tif_auto()        → Auto-download de TIF do CHC-UCSB
│   ├── find_chirps_files_for_period() → Localiza NetCDFs para período
│   ├── download_chirps_v3_file()   → Download NetCDF anual
│   ├── check_and_update_data()     → Verifica e atualiza arquivos
│   ├── get_data_status()           → Status de todos os arquivos
│   └── export_to_excel()           → Export Excel 4 abas
│
├── html_parser.py                  # Parser HTML de apólices (17 KB)
│   ├── parse_html_content()        → Extração completa de parâmetros
│   ├── _extract_cover_type()       → Tipo: precipitação vs temperatura
│   ├── _extract_period()           → Período start/end
│   ├── _extract_coordinates()      → GPS (4 métodos)
│   ├── _extract_financial_params() → Strike/Exit/Limit/Tick
│   └── calculate_parametric_claim() → Cálculo de sinistro
│
├── requirements.txt                # Dependências Python
├── Dockerfile                      # Container Docker
├── render.yaml                     # Deploy no Render.com
│
├── .github/
│   └── workflows/
│       ├── deploy-render.yml       # Auto-deploy no push
│       └── update-chirps-data.yml  # Atualização dia 15
│
├── templates/
│   ├── index.html                  # Interface principal
│   └── admin.html                  # Painel de administração
│
├── static/
│   ├── css/                        # Estilos CSS
│   ├── js/                         # JavaScript
│   └── img/                        # Imagens
│
├── scripts/
│   ├── download_initial_data.py    # Download inicial dados
│   └── start.sh                    # Script de startup
│
└── data/
    └── chirps_v3/
        ├── 2025/
        │   └── chirps-v3.0.rnl.2025.days_p05.nc  (~450 MB)
        ├── 2026/
        │   └── chirps-v3.0.rnl.2026.days_p05.nc  (baixado auto)
        └── tifs/
            ├── dec2025/             (31 TIFs × ~17 MB)
            ├── jan2026/             (31 TIFs)
            ├── feb2026/             (28 TIFs)
            └── mar2026/             (TIFs disponíveis = 10 em mar/2026)
```

---

## 17. Dependências Python

```
# Framework web
flask>=2.3.0,<4.0.0
gunicorn>=21.0.0

# Processamento de dados NetCDF / científico
numpy>=1.24.0
pandas>=2.0.0
xarray>=2023.1.0
h5netcdf>=1.1.0
netcdf4>=1.6.0
scipy>=1.10.0
openpyxl>=3.1.0

# Leitura de arquivos TIF
rasterio>=1.3.0          # CRÍTICO para extract_point_from_tif()

# Download de arquivos
requests>=2.31.0

# Utilitários
python-dotenv>=1.0.0
```

**Nota sobre `rasterio`:** A leitura de TIFs diários CHIRPS V3 requer `rasterio`. A instalação no Docker é gerenciada pelas dependências de sistema `libhdf5-dev` e `libnetcdf-dev`.

---

## 18. Histórico de Correções e Bugs Resolvidos

### Bug #1: Seleção Incorreta de Pixel TIF (CRÍTICO) — Resolvido em commit 89634f6

**Data:** 2025-03-12  
**Impacto:** Alto — resultados de precipitação incorretos para todas as coordenadas com fração de coluna > 0.5  
**Sintoma:** Precipitação total divergia de 7 a 22 mm em relação aos valores de referência

**Causa raiz:**
```python
# ANTES (bugado):
row, col = rasterio.transform.rowcol(transform, lon, lat, op=round)
# Python's round() usa "banker's rounding" (arredondamento bancário)
# round(2503.634) → 2504 (ERRADO para pixels com fração > 0.5)
```

**Correção:**
```python
# DEPOIS (correto):
col_float = (target_lon - src.transform.c) / src.transform.a
row_float = (target_lat - src.transform.f) / src.transform.e
col = math.floor(col_float)  # Seleciona o pixel que CONTÉM a coordenada
row = math.floor(row_float)
```

**Validação pós-correção:**
- Fábio 321: 219.84 → 226.91 mm ✅ (ref: 226.91)
- Fábio 322: 226.91 → 248.71 mm ✅ (ref: 248.71)  
- Jose Oneide 325: 246.41 → 237.13 mm ✅ (ref: 237.13)

### Bug #2: Coordenadas não retornadas no JSON da API — Resolvido em commit 89634f6

**Sintoma:** A resposta JSON de `/api/process` não incluía `latitude`, `longitude`, `pixel_latitude`, `pixel_longitude` no nível raiz.

**Correção:** Adicionados campos ao JSON de retorno:
```python
return jsonify({
    "success": True,
    "params": params,
    "latitude": lat,              # ← ADICIONADO
    "longitude": lon,             # ← ADICIONADO
    "pixel_latitude": pixel_lat_val,   # ← ADICIONADO
    "pixel_longitude": pixel_lon_val,  # ← ADICIONADO
    ...
})
```

### Bug #3: Erro xarray com numpy 2.x — Contornado

**Sintoma:** `packaging.version.Version(None)` ao importar xarray com numpy 2.4.3  
**Solução:** O sistema usa seu próprio `open_nc()` com fallback entre engines, que funciona corretamente mesmo com este bug do xarray.

### Informação: Dados Preliminares Nunca Utilizados

Por decisão metodológica, dados CHIRPS V3 **preliminares** (`prelim/sat`) **nunca são utilizados** no cálculo de sinistro. Apenas dados **finais gauge-adjusted** (`rnl`) são aceitos. Quando apenas dados preliminares estão disponíveis para um dia, esse dia é registrado como lacuna com status `aguardando_dados_finais`.

---

## Glossário

| Termo | Definição |
|---|---|
| CHIRPS | Climate Hazards Group InfraRed Precipitation with Stations |
| rnl | Dados finais gauge-adjusted (rain-gauge normalized) |
| prelim/sat | Dados preliminares baseados apenas em satélite (não gauge-adjusted) |
| byYear | Formato de arquivo NetCDF anual do CHIRPS V3 |
| NetCDF | Network Common Data Form — formato científico de dados gridados |
| TIF / GeoTIFF | Formato raster georreferenciado diário |
| Strike | Precipitação mínima contratual (gatilho do sinistro) |
| Exit Point | Precipitação mínima absoluta (piso do déficit) |
| Tick | Valor em BRL por milímetro de déficit |
| Limit | Indenização máxima em BRL |
| Haversine | Fórmula para distância geodésica entre dois pontos GPS |
| floor() | Função matemática que arredonda para baixo (inteiro inferior) |
| round() | Arredondamento padrão do Python (usa banker's rounding) |
| pixel centroide | Centro geométrico de um pixel do raster CHIRPS |
| coord_source | Método pelo qual as coordenadas foram extraídas do HTML |
| CHC-UCSB | Climate Hazards Center, University of California Santa Barbara |

---

*Documentação gerada em 2025-03-13. Commit atual: 89634f6. Branch: main.*
*Todos os resultados validados estão dentro da margem aceitável (≤ 0.005 mm de diferença).*
