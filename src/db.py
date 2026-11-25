"""
SQLite and Azure Blob Storage persistence layer for Govi Gnana.

This module is the single boundary that knows about SQLite and Azure Blob.
All credentials are resolved from environment variables or Streamlit secrets.
"""

import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

DB_PATH = "data/prices.db"
BLOB_NAME = "prices.db"
DEFAULT_CONTAINER = "agri-data"
BOOTSTRAP_CSV_PATH = "data/processed/crop_history.csv"


def _read_streamlit_secret(key: str):
    """Read a secret from Streamlit if available, without raising when absent."""
    try:
        import streamlit as st

        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return None


def get_connection_string() -> str:
    """Resolve the Azure Storage connection string from env or Streamlit secrets."""
    load_dotenv()
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or _read_streamlit_secret(
        "AZURE_STORAGE_CONNECTION_STRING"
    )
    if not conn_str:
        raise RuntimeError(
            "AZURE_STORAGE_CONNECTION_STRING is not set in environment, .env, or Streamlit secrets."
        )
    return conn_str


def get_container_name() -> str:
    """Resolve the Azure Blob container name, defaulting to 'agri-data'."""
    load_dotenv()
    return (
        os.environ.get("AZURE_STORAGE_CONTAINER_NAME")
        or _read_streamlit_secret("AZURE_STORAGE_CONTAINER_NAME")
        or DEFAULT_CONTAINER
    )


def get_connection(path: str = DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys enabled."""
    if path != ":memory:":
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create the canonical prices table and lookup index if they do not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prices (
            date        TEXT NOT NULL,
            category    TEXT,
            item        TEXT NOT NULL,
            unit        TEXT,
            market      TEXT NOT NULL,
            price_type  TEXT NOT NULL,
            price       REAL NOT NULL,
            PRIMARY KEY (date, item, market, price_type)
        );
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_prices_lookup
            ON prices (item, market, price_type, date);
        """
    )
    conn.commit()


def upsert_prices(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """
    Bulk-upsert canonical price rows into the prices table.
    Returns the number of rows processed.
    """
    if df is None or df.empty:
        return 0

    required = ["date", "item", "market", "price_type", "price"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns for upsert: {missing}")

    rows = [
        (
            str(row["date"]),
            None if pd.isna(row.get("category")) else str(row.get("category")),
            str(row["item"]),
            None if pd.isna(row.get("unit")) else str(row.get("unit")),
            str(row["market"]),
            str(row["price_type"]),
            float(row["price"]),
        )
        for _, row in df.iterrows()
    ]

    conn.executemany(
        """
        INSERT INTO prices (date, category, item, unit, market, price_type, price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date, item, market, price_type) DO UPDATE SET
            category = excluded.category,
            unit = excluded.unit,
            price = excluded.price;
        """,
        rows,
    )
    return len(rows)


def export_to_csv(conn: sqlite3.Connection, csv_path: str = BOOTSTRAP_CSV_PATH) -> None:
    """
    Write the prices table to CSV.
    Used by Phase 1's bootstrap shim so legacy CSV readers continue working unchanged.
    """
    parent = os.path.dirname(csv_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    df = pd.read_sql_query(
        """
        SELECT date, category, item, unit, market, price_type, price
        FROM prices
        ORDER BY category, item, market, price_type, date
        """,
        conn,
    )
    df.to_csv(csv_path, index=False)


def _get_blob_client():
    """Construct an Azure BlobClient for prices.db."""
    from azure.storage.blob import BlobServiceClient

    service_client = BlobServiceClient.from_connection_string(get_connection_string())
    return service_client.get_blob_client(container=get_container_name(), blob=BLOB_NAME)


def download_db_from_azure(local_path: str = DB_PATH) -> bool:
    """
    Download prices.db from Azure Blob Storage to local_path.
    Returns False if the blob does not exist yet (404), True on success.
    """
    from azure.core.exceptions import ResourceNotFoundError

    parent = os.path.dirname(local_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    blob_client = _get_blob_client()
    try:
        data = blob_client.download_blob().readall()
    except ResourceNotFoundError:
        return False

    with open(local_path, "wb") as f:
        f.write(data)
    return True


def upload_db_to_azure(local_path: str = DB_PATH) -> None:
    """Upload local_path to Azure Blob Storage, overwriting any existing blob."""
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Database file not found for upload: {local_path}")

    blob_client = _get_blob_client()
    with open(local_path, "rb") as f:
        blob_client.upload_blob(f, overwrite=True)


def restore_db_for_pipeline() -> bool:
    """Download prices.db from Azure for a pipeline run; returns False on first run."""
    return download_db_from_azure(DB_PATH)


def persist_db_after_pipeline() -> None:
    """Upload the updated prices.db to Azure after a pipeline run."""
    upload_db_to_azure(DB_PATH)


def bootstrap_for_app() -> None:
    """
    Phase 1 bootstrap shim for app.py:
    Ensure data/processed/crop_history.csv exists locally by downloading prices.db
    from Azure and exporting it if the CSV is missing.
    """
    if os.path.exists(BOOTSTRAP_CSV_PATH):
        return

    try:
        downloaded = download_db_from_azure(DB_PATH)
    except Exception as exc:
        raise RuntimeError(
            "No local data available and Azure could not be reached. "
            "Run `python -m scripts.one_time_migration` locally, or check Azure credentials."
        ) from exc

    if not downloaded:
        raise RuntimeError(
            "No data available in Azure Blob Storage. "
            "Run `python -m scripts.one_time_migration` locally, or check Azure credentials."
        )

    conn = get_connection(DB_PATH)
    try:
        init_schema(conn)
        export_to_csv(conn, BOOTSTRAP_CSV_PATH)
    finally:
        conn.close()
