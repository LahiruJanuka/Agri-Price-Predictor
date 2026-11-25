"""
src/pdf_parser.py
──────────────────
Extract CBSL Daily Price Report tables from PDF.

Two dates are present in every report:
  - report_date  : the publication date (today's column) — from the filename
  - prev_date    : the previous report's date             — extracted from PDF row 2

The previous date is NOT necessarily report_date - 1 day. It may be several
days earlier due to weekends, Poya days, or public holidays. Always read it
directly from the PDF rather than deriving it from the system date.
"""

import camelot
import pandas as pd
import re
import logging
from datetime import datetime
import os


# Date extraction helpers

_DATE_PATTERNS = [
    r"\b(\d{2})\.(\d{2})\.(\d{4})\b",   # DD.MM.YYYY  (primary CBSL format)
    r"\b(\d{4})-(\d{2})-(\d{2})\b",     # YYYY-MM-DD
    r"\b(\d{2})/(\d{2})/(\d{4})\b",     # DD/MM/YYYY
]


def _parse_date_string(text: str) -> datetime | None:
    """
    Try known date formats and return a datetime, or None if not parseable.
    Handles DD.MM.YYYY (primary CBSL format), YYYY-MM-DD, DD/MM/YYYY.
    """
    if not text:
        return None
    text = text.strip()

    for pattern in _DATE_PATTERNS:
        m = re.search(pattern, text)
        if not m:
            continue
        g = m.groups()
        try:
            if len(g[0]) == 4:          # YYYY-MM-DD
                return datetime(int(g[0]), int(g[1]), int(g[2]))
            else:                        # DD.MM.YYYY or DD/MM/YYYY
                return datetime(int(g[2]), int(g[1]), int(g[0]))
        except ValueError:
            continue
    return None


def extract_report_dates(df: pd.DataFrame, filename_date: str) -> tuple[str, str | None]:
    """
    Scan the first few rows of the raw camelot DataFrame to find the actual
    date strings printed in the PDF header.

    Returns (report_date, prev_date) as 'YYYY-MM-DD' strings.
    - report_date  : always the filename-derived publication date (authoritative).
    - prev_date    : the earlier date found in the PDF header; None if unreadable.

    The PDF layout (from real CBSL reports) looks like:
        row 0 : label row  — e.g. "Last Friday", "Yesterday", "", ...
        row 1 : label row  — e.g. "Today", "", ...
        row 2 : date row   — e.g. "20.11.2026", "", ...   ← previous date strings

    We scan rows 0-4 for any cell matching a date pattern, collect unique
    dates, exclude the report_date itself, and take the most recent of the rest.
    """
    report_dt = datetime.strptime(filename_date, "%Y-%m-%d")
    found_dates: set[datetime] = set()

    for row_idx in range(min(5, len(df))):
        row = df.iloc[row_idx]
        for cell in row:
            dt = _parse_date_string(str(cell))
            if dt is not None:
                found_dates.add(dt)

    # Remove the report date itself (it appears in the filename, not the PDF header dates)
    candidate_prev = [d for d in found_dates if d < report_dt]

    if not candidate_prev:
        logging.warning(
            "Could not extract a previous-report date from PDF header. "
            "Filename date: %s. Cells scanned: %s",
            filename_date,
            [str(df.iloc[r]) for r in range(min(5, len(df)))]
        )
        return filename_date, None

    prev_dt = max(candidate_prev)   # most recent date before report date

    # Sanity: prev must be strictly before report
    if prev_dt >= report_dt:
        logging.warning(
            "Extracted previous date %s is not before report date %s — ignoring.",
            prev_dt.date(), report_dt.date()
        )
        return filename_date, None

    prev_date_str = prev_dt.strftime("%Y-%m-%d")
    logging.info(
        "PDF dates extracted — report: %s, previous: %s", filename_date, prev_date_str
    )
    return filename_date, prev_date_str


# Public API
def parse_cbsl_pdf(pdf_path: str) -> pd.DataFrame:
    """
    Extract the full price table from CBSL PDF (page 2) using stream flavour.

    Sets two date columns on the returned DataFrame:
      - report_date : publication date (YYYY-MM-DD), from the filename
      - prev_date   : previous-report date (YYYY-MM-DD), from the PDF header;
                      None/NaN if the PDF header could not be read reliably.

    The downstream data_cleaner uses both columns to assign prices to their
    actual reporting dates instead of assuming consecutive calendar days.
    """
    tables = camelot.read_pdf(pdf_path, pages="2", flavor="stream")
    if not tables:
        raise Exception("No tables found in PDF page 2.")

    df = tables[0].df
    df.columns = [f"col_{i}" for i in range(df.shape[1])]

    # Derive report_date from filename
    filename = os.path.basename(pdf_path)
    date_match = re.search(r"price_report_(\d{8})", filename)
    if date_match:
        report_date = datetime.strptime(date_match.group(1), "%Y%m%d").strftime("%Y-%m-%d")
    else:
        report_date = datetime.now().strftime("%Y-%m-%d")
        logging.warning(
            "Could not extract date from filename '%s'. Falling back to system date.", filename
        )

    # Extract previous-report date from PDF header 
    _, prev_date = extract_report_dates(df, report_date)

    df["report_date"] = report_date
    df["prev_date"] = prev_date   # may be None → stored as NaN

    return df


def parse_pdf_to_csv(pdf_path: str, output_csv: str) -> None:
    df = parse_cbsl_pdf(pdf_path)
    report_date_val = df["report_date"].iloc[0]

    if os.path.exists(output_csv) and os.path.getsize(output_csv) > 0:
        master = pd.read_csv(output_csv)
        if not master[master["report_date"] == report_date_val].empty:
            logging.info(
                "Data for %s already exists in raw CSV. Skipping.", report_date_val
            )
            return
        master = pd.concat([master, df], ignore_index=True)
    else:
        master = df

    master.to_csv(output_csv, index=False)
    logging.info("Appended raw data to %s", output_csv)
