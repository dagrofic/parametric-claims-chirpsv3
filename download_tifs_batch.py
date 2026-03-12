#!/usr/bin/env python3
"""
Download em lote dos TIFs CHIRPS V3 necessários para um período.
Uso: python3 download_tifs_batch.py [start_date] [end_date]
Ex:  python3 download_tifs_batch.py 2025-10-15 2025-11-30
"""
import sys
import os
import logging
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger("tif_downloader")

CHIRPS_V3_TIF_BASE_DIR = os.path.join(os.path.dirname(__file__), "data", "chirps_v3", "tifs")

MONTH_ABBR = {
    1: "jan", 2: "feb", 3: "mar", 4: "apr",
    5: "may", 6: "jun", 7: "jul", 8: "aug",
    9: "sep", 10: "oct", 11: "nov", 12: "dec"
}

def download_tifs_for_period(start_date: str, end_date: str, tif_base_dir: str = None):
    """Baixa todos os TIFs finais (rnl) para o período especificado."""
    if tif_base_dir is None:
        tif_base_dir = CHIRPS_V3_TIF_BASE_DIR

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt   = datetime.strptime(end_date,   "%Y-%m-%d")

    current = start_dt
    total = (end_dt - start_dt).days + 1
    downloaded = 0
    skipped = 0
    failed = 0

    logger.info(f"Iniciando download de {total} TIFs: {start_date} → {end_date}")

    while current <= end_dt:
        y, m, d = current.year, current.month, current.day
        month_dir_name = f"{MONTH_ABBR[m]}{y}"
        month_dir = os.path.join(tif_base_dir, month_dir_name)
        os.makedirs(month_dir, exist_ok=True)

        fname = f"chirps-v3.0.rnl.{y}.{m:02d}.{d:02d}.tif"
        local_path = os.path.join(month_dir, fname)

        if os.path.exists(local_path) and os.path.getsize(local_path) > 10000:
            skipped += 1
            current += timedelta(days=1)
            continue

        url = f"https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/{y}/{fname}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CHIRPSv3-Batch/3.0"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
            if len(data) > 10000:
                with open(local_path, "wb") as f:
                    f.write(data)
                downloaded += 1
                if downloaded % 5 == 0 or downloaded == 1:
                    logger.info(f"  [{downloaded}/{total}] ✓ {fname} ({len(data)//1024} KB)")
            else:
                logger.warning(f"  Arquivo pequeno demais: {fname} ({len(data)} bytes)")
                failed += 1
        except Exception as e:
            logger.warning(f"  ✗ Falha: {fname} — {e}")
            failed += 1

        current += timedelta(days=1)

    logger.info(f"\n{'='*50}")
    logger.info(f"Download concluído:")
    logger.info(f"  ✓ Novos: {downloaded}")
    logger.info(f"  → Já existiam: {skipped}")
    logger.info(f"  ✗ Falhas: {failed}")
    logger.info(f"  Total: {total} dias")
    return downloaded, skipped, failed

if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "2025-10-15"
    end   = sys.argv[2] if len(sys.argv) > 2 else "2025-11-30"
    download_tifs_for_period(start, end)
