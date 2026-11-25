import logging
import pandas as pd
from .data_fetcher import fetch_today_pdf
from .pdf_parser import parse_pdf_to_csv
from .data_cleaner import run_data_cleaning_pipeline
from .utils import setup_logging, ensure_dir
from .db import (
    DB_PATH,
    get_connection,
    init_schema,
    upsert_prices,
    restore_db_for_pipeline,
    persist_db_after_pipeline,
    export_to_csv,
)

CANONICAL_COLS = ["date", "category", "item", "unit", "market", "price_type", "price"]
HISTORY_CSV = "data/processed/crop_history.csv"


def run_pipeline():
    setup_logging()
    ensure_dir("data/processed")

    # Phase 1: Download and parse PDF into raw format
    pdf_path = fetch_today_pdf()
    raw_csv = "data/processed/cbsl_prices_raw.csv"
    parse_pdf_to_csv(pdf_path, raw_csv)

    # Phase 2: Clean, reshape, and feature engineer across all categories
    run_data_cleaning_pipeline(raw_csv, HISTORY_CSV)

    logging.info("Full pipeline (Phase 1 + Phase 2) completed successfully.")


def run_full_pipeline_with_storage():
    """
    Storage-aware wrapper around run_pipeline().

    Steps:
      1. Download prices.db from Azure (bootstrap so legacy cleaner has full history).
      2. Export DB → crop_history.csv (shim for data_cleaner which still reads CSV).
      3. Run the existing PDF → CSV pipeline.
      4. Read the updated crop_history.csv, upsert into prices.db.
      5. Upload prices.db back to Azure.
    """
    setup_logging()
    ensure_dir("data/processed")

    # 1. Restore DB from Azure
    logging.info("[storage] Restoring prices.db from Azure …")
    restore_db_for_pipeline()

    # 2. Export existing DB rows → CSV (so data_cleaner can merge history)
    import os
    if os.path.exists(DB_PATH):
        logging.info("[storage] Exporting DB → %s …", HISTORY_CSV)
        conn = get_connection(DB_PATH)
        try:
            export_to_csv(conn, HISTORY_CSV)
        finally:
            conn.close()

    # 3. Run the standard PDF pipeline (updates crop_history.csv)
    run_pipeline()

    # 4. Upsert the freshly updated CSV rows into the DB
    logging.info("[storage] Upserting %s → prices.db …", HISTORY_CSV)
    df = pd.read_csv(HISTORY_CSV)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df[[c for c in CANONICAL_COLS if c in df.columns]]
    conn = get_connection(DB_PATH)
    try:
        init_schema(conn)
        count = upsert_prices(conn, df)
        conn.commit()
        logging.info("[storage] Upserted %d rows into prices.db.", count)
    finally:
        conn.close()

    # 5. Push updated DB back to Azure
    logging.info("[storage] Persisting prices.db to Azure …")
    persist_db_after_pipeline()
    logging.info("[storage] Pipeline with storage complete.")


if __name__ == "__main__":
    run_pipeline()
