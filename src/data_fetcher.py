"""
src/data_fetcher.py
────────────────────
CBSL Daily Price Report downloader.

Primary strategy  : date-based URL discovery (observed naming convention).
Fallback strategy : HTML scraping of the official CBSL listing page.

Both strategies use the existing Cloudflare relay and produce a local PDF path
that is consumed unchanged by the downstream parsing pipeline.
"""

import logging
import os
import re
from datetime import date, datetime, timedelta

import requests
from bs4 import BeautifulSoup

from .utils import ensure_dir

CBSL_LISTING_URL = "https://www.cbsl.gov.lk/en/statistics/economic-indicators/price-report"
CBSL_PDF_BASE_URL = (
    "https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/"
    "statistics/pricerpt/price_report_{date}_e.pdf"
)
PDF_DIR = "data/raw_pdfs"
MAX_LOOKBACK_DAYS = 14      # calendar days to search backwards
REQUEST_TIMEOUT = 30        # seconds
PDF_MAGIC = b"%PDF-"        # file-signature for content validation

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; GoviGnanaBot/1.0; "
        "+https://github.com/agri_price_predictor)"
    )
}

def _date_to_url(report_date: date) -> str:
    """Build the candidate PDF URL for *report_date* using the observed convention."""
    return CBSL_PDF_BASE_URL.format(date=report_date.strftime("%Y%m%d"))


def _is_valid_pdf(content: bytes) -> bool:
    """Return True if *content* starts with the PDF magic bytes."""
    return content[:5] == PDF_MAGIC


def _local_path_for_date(date_str: str) -> str:
    return os.path.join(PDF_DIR, f"price_report_{date_str}.pdf")


def _existing_valid_pdf(date_str: str) -> str | None:
    """Return the local path if a valid PDF already exists for *date_str*."""
    path = _local_path_for_date(date_str)
    if os.path.exists(path):
        with open(path, "rb") as fh:
            if fh.read(5) == PDF_MAGIC:
                return path
    return None


def _save_pdf(content: bytes, date_str: str) -> str:
    """Write *content* to the standard local path and return that path."""
    ensure_dir(PDF_DIR)
    path = _local_path_for_date(date_str)
    with open(path, "wb") as fh:
        fh.write(content)
    return path


def _try_date_url(report_date: date) -> str | None:
    """
    Attempt to fetch the CBSL PDF for *report_date* via the date-based URL.

    Returns the local file path on success, None on HTTP 404.
    Raises for access restrictions or server errors that must not be silently skipped.
    """
    date_str = report_date.strftime("%Y%m%d")

    cached = _existing_valid_pdf(date_str)
    if cached:
        logging.info("[date-strategy] Reusing existing PDF: %s", cached)
        return cached

    url = _date_to_url(report_date)
    logging.debug("[date-strategy] Trying %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc}") from exc

    if resp.status_code == 404:
        logging.debug("[date-strategy] 404 for %s — skipping", date_str)
        return None

    if resp.status_code == 403:
        raise PermissionError(
            f"HTTP 403 Forbidden for PDF {date_str}. "
            "CBSL may have restricted access; not treating as missing report."
        )

    if resp.status_code == 429:
        raise RuntimeError(
            f"HTTP 429 Too Many Requests for PDF {date_str}. "
            "Backing off — do not retry immediately."
        )

    if resp.status_code >= 500:
        raise RuntimeError(
            f"HTTP {resp.status_code} server error for PDF {date_str}."
        )

    resp.raise_for_status()

    content = resp.content
    if not _is_valid_pdf(content):
        logging.warning("[date-strategy] Response for %s is not a valid PDF — skipping", date_str)
        return None

    path = _save_pdf(content, date_str)
    logging.info("[date-strategy] Downloaded PDF for %s → %s", date_str, path)
    return path


def _fetch_by_date(max_lookback: int = MAX_LOOKBACK_DAYS) -> str:
    """
    Walk backwards from yesterday up to *max_lookback* days.
    Returns the first valid PDF path found, or raises FileNotFoundError.
    Hard errors (403, 429, 5xx, network) propagate immediately.
    """
    today = date.today()

    for days_back in range(1, max_lookback + 1):
        candidate = today - timedelta(days=days_back)
        result = _try_date_url(candidate)   # raises on hard errors
        if result is not None:
            return result

    raise FileNotFoundError(
        f"Date-based strategy: no PDF found in the last {max_lookback} days."
    )


# Fallback strategy: HTML scraping
def get_latest_pdf_url() -> str:
    """Scrape the CBSL listing page and return the URL of the latest PDF."""
    resp = requests.get(CBSL_LISTING_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "price_report" in href and href.endswith(".pdf"):
            if not href.startswith("http"):
                href = "https://www.cbsl.gov.lk" + href
            pdf_links.append(href)

    if not pdf_links:
        raise Exception("HTML fallback: no PDF link found on the CBSL listing page.")

    return pdf_links[0]


def download_pdf(url: str, save_path: str) -> str:
    """Download *url*, validate it is a real PDF, and write to *save_path*."""
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()

    content = resp.content
    if not _is_valid_pdf(content):
        raise ValueError(f"Response from {url} is not a valid PDF.")

    ensure_dir(os.path.dirname(save_path))
    with open(save_path, "wb") as fh:
        fh.write(content)
    return save_path


def _fetch_by_html() -> str:
    """HTML-scraping fallback: find latest PDF on CBSL listing page and download."""
    logging.info("[html-fallback] Fetching CBSL listing page …")
    pdf_url = get_latest_pdf_url()
    logging.info("[html-fallback] Found PDF URL: %s", pdf_url)

    date_match = re.search(r"price_report_(\d{8})", pdf_url)
    date_str = (
        date_match.group(1)
        if date_match
        else (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    )

    cached = _existing_valid_pdf(date_str)
    if cached:
        logging.info("[html-fallback] Reusing existing PDF: %s", cached)
        return cached

    save_path = _local_path_for_date(date_str)
    download_pdf(pdf_url, save_path)
    logging.info("[html-fallback] Saved PDF → %s", save_path)
    return save_path


def fetch_today_pdf(max_lookback: int = MAX_LOOKBACK_DAYS) -> str:
    """
    Download the most recent CBSL Daily Price Report and return its local path.

    1. Tries date-based URL discovery (primary).
    2. Falls back to HTML scraping only on FileNotFoundError (lookback exhausted).
    Hard errors (403, 429, 5xx, network) are re-raised without fallback.
    """
    ensure_dir(PDF_DIR)

    try:
        return _fetch_by_date(max_lookback=max_lookback)
    except FileNotFoundError as exc:
        logging.warning("[fetch] Date-based strategy exhausted: %s — trying HTML fallback.", exc)

    try:
        return _fetch_by_html()
    except Exception as html_exc:
        raise RuntimeError(
            "Both PDF discovery strategies failed.\n"
            f"  HTML fallback error: {html_exc}"
        ) from html_exc
