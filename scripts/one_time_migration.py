"""
scripts/one_time_migration.py
─────────────────────────────
One-time migration: crop_history.csv → prices.db (SQLite) → Azure Blob.

Run once from the project root:
    python -m scripts.one_time_migration

Prerequisites:
  - .env contains AZURE_STORAGE_CONNECTION_STRING
  - src/db.py exists
  - data/processed/crop_history.csv exists
  - azure-storage-blob is installed  (pip install azure-storage-blob==12.24.1)

The script REFUSES to overwrite an existing prices.db.
"""

import os
import sys
import pandas as pd

# ── Ensure project root is on sys.path when run via python -m ─────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.db import (
    DB_PATH,
    get_connection,
    init_schema,
    upsert_prices,
    upload_db_to_azure,
)

# ── Constants ─────────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "crop_history.csv")
CANONICAL_COLS = ["date", "category", "item", "unit", "market", "price_type", "price"]

KNOWN_MARKETS = {
    "Pettah", "Dambulla", "Narahenpita",
    "Peliyagoda", "Negombo", "Marandagahamula",
}


def _load_and_validate_csv(csv_path: str) -> pd.DataFrame:
    """Load CSV, keep only canonical columns, validate, return clean DataFrame."""
    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"Source CSV not found: {csv_path}\n"
            "Run the pipeline at least once to generate crop_history.csv first."
        )

    df = pd.read_csv(csv_path)

    missing = [c for c in CANONICAL_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV is missing required columns: {missing}")

    df = df[CANONICAL_COLS].copy()

    # Normalize date to YYYY-MM-DD string
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

    # Basic sanity checks
    null_rows = df[df[["date", "item", "market", "price_type", "price"]].isnull().any(axis=1)]
    if not null_rows.empty:
        raise ValueError(f"CSV has {len(null_rows)} rows with NULL in required fields.")

    bad_markets = set(df["market"].unique()) - KNOWN_MARKETS
    if bad_markets:
        raise ValueError(
            f"CSV contains unrecognised markets (combined names?): {bad_markets}\n"
            "Fix data_cleaner.py before migrating."
        )

    return df


def main() -> None:
    print("=" * 60)
    print("Govi Gnana — One-Time Data Migration")
    print("=" * 60)

    # ── Guard: refuse to overwrite existing DB ─────────────────────────────
    if os.path.exists(DB_PATH):
        print(f"\n[SKIP] {DB_PATH} already exists — migration has already run.")
        print("Delete it manually if you want to re-migrate from scratch.")
        sys.exit(0)

    # ── Step 1: Load & validate CSV ────────────────────────────────────────
    print(f"\n[1/4] Loading {CSV_PATH} …")
    df = _load_and_validate_csv(CSV_PATH)
    print(f"      Loaded {len(df):,} rows | markets: {sorted(df['market'].unique())}")

    # ── Step 2: Create SQLite DB and upsert rows ───────────────────────────
    print(f"\n[2/4] Creating {DB_PATH} and inserting rows …")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_connection(DB_PATH)
    try:
        init_schema(conn)
        inserted = upsert_prices(conn, df)
        conn.commit()
        print(f"      Inserted/upserted {inserted:,} rows.")
    finally:
        conn.close()

    # ── Step 3: Verify row count matches source ────────────────────────────
    print("\n[3/4] Verifying row count …")
    import sqlite3
    verify_conn = sqlite3.connect(DB_PATH)
    db_count = verify_conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    verify_conn.close()

    if db_count != len(df):
        raise RuntimeError(
            f"Row count mismatch! CSV={len(df)}, DB={db_count}. "
            "Inspect the DB before uploading."
        )
    print(f"      DB row count matches CSV: {db_count:,} rows ✓")

    # ── Step 4: Upload to Azure Blob ───────────────────────────────────────
    print("\n[4/4] Uploading prices.db to Azure Blob Storage …")
    upload_db_to_azure(DB_PATH)
    print("      Upload complete ✓")

    print("\n" + "=" * 60)
    print("Migration finished successfully.")
    print(f"  Local DB : {DB_PATH}")
    print(f"  Azure    : container=agri-data  blob=prices.db")
    print("=" * 60)


if __name__ == "__main__":
    main()
