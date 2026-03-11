#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Download Inicial — CHIRPS V3.0
=========================================
Baixa os arquivos NetCDF necessários para o sistema paramétrico.

Uso:
    python scripts/download_initial_data.py
    python scripts/download_initial_data.py --years 2025 2026
    python scripts/download_initial_data.py --force  # Re-baixar mesmo se existe

Fonte: https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/

Autor: Sistema Paramétrico V3 - dagrofic
"""

import sys
import os
import argparse
import requests
from pathlib import Path
from datetime import datetime

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ═══════════════════════════════════════════════════════════
# CONFIGURAÇÃO
# ═══════════════════════════════════════════════════════════

CHIRPS_V3_BASE_URL = "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/"
DEFAULT_DATA_DIR   = os.environ.get("CHIRPS_DATA_DIR", "./data/chirps_v3")
CHUNK_SIZE         = 1024 * 1024  # 1 MB chunks para download


# ═══════════════════════════════════════════════════════════
# FUNÇÕES
# ═══════════════════════════════════════════════════════════

def format_size(bytes_val: int) -> str:
    """Formata tamanho em bytes para formato legível"""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024
    return f"{bytes_val:.1f} TB"


def check_url_available(url: str) -> bool:
    """Verifica se URL existe e retorna True/False"""
    try:
        resp = requests.head(url, timeout=30, allow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


def download_file(url: str, dest_path: Path, force: bool = False) -> bool:
    """
    Baixa arquivo com barra de progresso.
    
    Returns:
        True se sucesso, False se falha
    """
    if dest_path.exists() and not force:
        size_mb = dest_path.stat().st_size / 1024 / 1024
        if size_mb > 1:
            print(f"  ✅ Já existe: {dest_path.name} ({size_mb:.1f} MB) — use --force para re-baixar")
            return True

    # Verificar disponibilidade
    print(f"  🔍 Verificando: {url}")
    if not check_url_available(url):
        print(f"  ❌ Arquivo não disponível no servidor (404 ou timeout)")
        print(f"     URL: {url}")
        return False

    print(f"  ⬇  Baixando: {url}")

    try:
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0

        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with open(dest_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    if total_size > 0:
                        pct = downloaded / total_size * 100
                        done_mb = downloaded / 1024 / 1024
                        total_mb = total_size / 1024 / 1024
                        bar_len = 40
                        filled = int(bar_len * downloaded / total_size)
                        bar = "█" * filled + "░" * (bar_len - filled)
                        print(f"\r  [{bar}] {pct:.1f}% — {done_mb:.1f}/{total_mb:.1f} MB", end="", flush=True)

        print()  # Nova linha após barra de progresso

        final_size = dest_path.stat().st_size / 1024 / 1024
        print(f"  ✅ Download concluído: {dest_path.name} ({final_size:.1f} MB)")
        return True

    except requests.exceptions.HTTPError as e:
        print(f"\n  ❌ Erro HTTP: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False
    except KeyboardInterrupt:
        print(f"\n  ⚠️  Download interrompido pelo usuário")
        if dest_path.exists():
            dest_path.unlink()
        sys.exit(0)
    except Exception as e:
        print(f"\n  ❌ Erro: {e}")
        if dest_path.exists():
            dest_path.unlink()
        return False


def download_year(year: int, data_dir: Path, force: bool = False) -> bool:
    """Baixa arquivo anual CHIRPS V3 para o ano especificado"""
    fname = f"chirps-v3.0.rnl.{year}.days_p05.nc"
    url   = f"{CHIRPS_V3_BASE_URL}{fname}"
    dest  = data_dir / str(year) / fname
    return download_file(url, dest, force)


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Download de dados CHIRPS V3.0 para o sistema paramétrico",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python scripts/download_initial_data.py
  python scripts/download_initial_data.py --years 2025 2026
  python scripts/download_initial_data.py --years 2024 --force
  
Fonte de dados:
  https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/
        """
    )
    parser.add_argument(
        "--years", nargs="+", type=int,
        help="Anos para baixar (padrão: ano atual e anterior)"
    )
    parser.add_argument(
        "--data-dir", default=DEFAULT_DATA_DIR,
        help=f"Diretório de destino (padrão: {DEFAULT_DATA_DIR})"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-baixar mesmo se arquivo já existe"
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Apenas verificar disponibilidade, sem baixar"
    )

    args = parser.parse_args()

    # Determinar anos
    current_year = datetime.now().year
    if args.years:
        years = sorted(set(args.years))
    else:
        years = [current_year - 1, current_year]

    data_dir = Path(args.data_dir)

    # ── Header ─────────────────────────────────────────────
    print()
    print("=" * 62)
    print("  CHIRPS V3.0 — Download de Dados Paramétricos")
    print("=" * 62)
    print(f"  Fonte: {CHIRPS_V3_BASE_URL}")
    print(f"  Destino: {data_dir.absolute()}")
    print(f"  Anos: {', '.join(map(str, years))}")
    print(f"  Forçar re-download: {'Sim' if args.force else 'Não'}")
    print("=" * 62)
    print()

    # ── Verificar espaço em disco ───────────────────────────
    try:
        import shutil
        total, used, free = shutil.disk_usage(str(data_dir.parent))
        free_gb = free / 1024**3
        needed_gb = len(years) * 0.5  # ~500 MB por ano
        print(f"💾 Espaço livre: {free_gb:.1f} GB (necessário: ~{needed_gb:.1f} GB)")
        if free_gb < needed_gb:
            print(f"⚠️  ATENÇÃO: Espaço em disco pode ser insuficiente!")
        print()
    except Exception:
        pass

    # ── Processar cada ano ──────────────────────────────────
    results = {}

    for year in years:
        print(f"📂 Ano {year}:")

        fname = f"chirps-v3.0.rnl.{year}.days_p05.nc"
        url   = f"{CHIRPS_V3_BASE_URL}{fname}"

        if args.check_only:
            available = check_url_available(url)
            status = "✅ Disponível" if available else "❌ Não disponível"
            print(f"  {status}: {url}")
            results[year] = available
        else:
            success = download_year(year, data_dir, force=args.force)
            results[year] = success

        print()

    # ── Resumo ──────────────────────────────────────────────
    print("=" * 62)
    print("  RESUMO")
    print("=" * 62)

    success_count = sum(1 for v in results.values() if v)
    for year, success in results.items():
        icon = "✅" if success else "❌"
        if success:
            path = data_dir / str(year) / f"chirps-v3.0.rnl.{year}.days_p05.nc"
            size = f"({path.stat().st_size/1024/1024:.1f} MB)" if path.exists() else ""
            print(f"  {icon} {year}: OK {size}")
        else:
            print(f"  {icon} {year}: FALHOU ou não disponível ainda")

    print()
    print(f"  Total: {success_count}/{len(years)} anos processados com sucesso")

    if success_count > 0:
        print()
        print("🚀 Dados prontos! Inicie o sistema com:")
        print("   python app.py")
        print()
        print("   Ou em produção com Gunicorn:")
        print("   gunicorn --bind 0.0.0.0:5000 --workers 2 app:app")

    print("=" * 62)
    print()

    return 0 if success_count == len(years) else 1


if __name__ == "__main__":
    sys.exit(main())
