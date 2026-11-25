import logging
from os.path import exists

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import os
from .utils import ensure_dir

CBSL_URL = "https://www.cbsl.gov.lk/en/statistics/economic-indicators/price-report"
PDF_DIR = "data/raw_pdfs"

# Headers that make requests look like a normal browser fetch.
# CBSL rejects requests with the default python-requests UA.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}

def get_latest_pdf_url():
    """Fetch the URL of the latest price report PDF from the CBSL website"""
    resp = requests.get(CBSL_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')

    # Find all anchor tags with href containing "price report"
    pdf_links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if 'price_report' in href and href.endswith('.pdf'):
            # Ensure full URL
            if not href.startswith('http'):
                href = 'https://www.cbsl.gov.lk' + href
            pdf_links.append(href)

    if not pdf_links:
        raise Exception("No PDF link found on the page.")

    # Usually the latest is the first one, but we sort by date in file name if possible
    # For simplicity, take the first link assuming first is the latest
    return pdf_links[0]

def download_pdf(url, save_path):
    """Download PDF from URL and save to the save_path."""
    resp = requests.get(url, headers=HEADERS, timeout=30, stream=True)
    resp.raise_for_status()
    with open(save_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return save_path

def fetch_today_pdf():
    """Download today's PDF and return the file path with its true document date."""
    import re
    ensure_dir(PDF_DIR)
    pdf_url = get_latest_pdf_url()
    
    # Extract the date string from the URL (e.g., matching '20260617')
    date_match = re.search(r'price_report_(\d{8})', pdf_url)
    if date_match:
        doc_date_str = date_match.group(1) # e.g., "20260617"
    else:
        # Fallback to yesterday if the pattern fails for some reason
        doc_date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        
    save_path = os.path.join(PDF_DIR, f"price_report_{doc_date_str}.pdf")

    if os.path.exists(save_path):
        logging.info(f"PDF already exists: {save_path}")
    else:
        logging.info(f"Downloading PDF from {pdf_url}")
        download_pdf(pdf_url, save_path)
        logging.info(f"Saved to {save_path}")

    return save_path  
