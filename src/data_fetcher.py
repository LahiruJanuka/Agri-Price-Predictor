import logging
from os.path import exists

import requests
from bs4 import BeautifulSoup
from datetime import datetime
import os
from .utils import ensure_dir

CBSL_URL = "https://www.cbsl.gov.lk/en/statistics/economic-indicators/price-report"
PDF_DIR = "data/raw_pdfs"

def get_latest_pdf_url():
    """Fetch the URL of the latest price report PDF from the CBSL website"""
    resp = requests.get(CBSL_URL)
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
    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(save_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)
    return save_path

def fetch_today_pdf():
    """Download today's PDF and return the file path."""
    ensure_dir(PDF_DIR)
    pdf_url = get_latest_pdf_url()
    today_str = datetime.now().strftime("%Y%m%d")
    save_path = os.path.join(PDF_DIR, f"price_report_{today_str}.pdf")

    if os.path.exists(save_path):
        logging.info(f"PDF already exists: {save_path}")
    else:
        logging.info(f"Downloading PDF from {pdf_url}")
        download_pdf(pdf_url, save_path)
        logging.info(f"Saved to {save_path}")

    return save_path
    
