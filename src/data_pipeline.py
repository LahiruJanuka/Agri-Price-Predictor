import logging
from .data_fetcher import fetch_today_pdf
from .pdf_parser import parse_pdf_to_csv
from .data_cleaner import run_data_cleaning_pipeline
from .utils import setup_logging, ensure_dir

def run_pipeline():
    setup_logging()
    ensure_dir("data/processed")
    
    # Phase 1: Download and parse PDF into raw format
    pdf_path = fetch_today_pdf()
    raw_csv = "data/processed/cbsl_prices_raw.csv"
    parse_pdf_to_csv(pdf_path, raw_csv)
    
    # Phase 2: Clean, reshape, and feature engineer across all categories
    output_csv = "data/processed/crop_history.csv"
    run_data_cleaning_pipeline(raw_csv, output_csv)  # Updated function call here
    
    logging.info("Full pipeline (Phase 1 + Phase 2) completed successfully.")

if __name__ == "__main__":
    run_pipeline()
