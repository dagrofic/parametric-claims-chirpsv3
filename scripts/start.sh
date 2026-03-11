#!/bin/bash
# ============================================================
# start.sh — Script de inicialização para Render / Docker
# ============================================================

set -e

echo "========================================="
echo "  CHIRPS V3.0 Paramétrico — Startup"
echo "========================================="

# Criar diretórios de dados
mkdir -p "${CHIRPS_DATA_DIR:-/data/chirps_v3}/2025"
mkdir -p "${CHIRPS_DATA_DIR:-/data/chirps_v3}/2026"
mkdir -p "${CHIRPS_DATA_DIR:-/data/chirps_v3}/2027"
echo "✅ Diretórios de dados criados"

# Verificar status dos dados
CURRENT_YEAR=$(date +%Y)
PREV_YEAR=$((CURRENT_YEAR - 1))
DATA_BASE="${CHIRPS_DATA_DIR:-/data/chirps_v3}"

echo ""
echo "📁 Verificando dados CHIRPS V3..."
for year in $PREV_YEAR $CURRENT_YEAR; do
    FILE="$DATA_BASE/$year/chirps-v3.0.rnl.$year.days_p05.nc"
    if [ -f "$FILE" ]; then
        SIZE=$(du -sh "$FILE" | cut -f1)
        echo "  ✅ $year: $FILE ($SIZE)"
    else
        echo "  ⚠️  $year: arquivo não encontrado — use o painel Admin para baixar"
    fi
done

echo ""
echo "🚀 Iniciando servidor Flask..."
echo "   PORT: ${PORT:-5000}"
echo "   CHIRPS_DATA_DIR: ${CHIRPS_DATA_DIR:-/data/chirps_v3}"
echo ""

# Iniciar com Gunicorn
exec gunicorn \
    --bind "0.0.0.0:${PORT:-5000}" \
    --workers "${WORKERS:-2}" \
    --timeout "${TIMEOUT:-120}" \
    --access-logfile - \
    --error-logfile - \
    --log-level info \
    --preload \
    app:app
