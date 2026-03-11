# ============================================================
# Dockerfile — CHIRPS V3.0 Paramétrico
# Sistema de Regulação de Sinistros Paramétricos
# ============================================================

FROM python:3.11-slim

# Metadados
LABEL maintainer="dagrofic"
LABEL description="Sistema de Regulação de Sinistros Paramétricos — CHIRPS V3.0"
LABEL version="3.0.0"

# Variáveis de ambiente
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5000 \
    FLASK_DEBUG=false \
    CHIRPS_DATA_DIR=/app/data/chirps_v3

# Diretório de trabalho
WORKDIR /app

# Dependências do sistema para h5netcdf/netcdf4
RUN apt-get update && apt-get install -y --no-install-recommends \
    libhdf5-dev \
    libnetcdf-dev \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Criar diretórios necessários
RUN mkdir -p data/chirps_v3/2025 \
             data/chirps_v3/2026 \
             data/chirps_v3/2027 \
             logs

# Permissões
RUN chmod +x scripts/*.sh 2>/dev/null || true

# Porta
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/ || exit 1

# Comando de inicialização com Gunicorn
CMD gunicorn --bind 0.0.0.0:${PORT} \
             --workers 2 \
             --timeout 120 \
             --access-logfile - \
             --error-logfile - \
             --log-level info \
             app:app
