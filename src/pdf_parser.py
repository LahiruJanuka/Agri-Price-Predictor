import camelot
import pandas as pd
import re
import logging
from datetime import datetime
import os

def parse_cbsl_pdf(pdf_path):
    """
    Extract the full price table from CBSL PDF (page 2) using stream flavor
    and extract the true report date directly from the filename structure.
    """
    tables = camelot.read_pdf(pdf_path, pages='2', flavor='stream')
    if not tables:
        raise Exception("No tables found in PDF page 2.")

    df = tables[0].df

    # Force generic column names to prevent multi-level header mismatches
    df.columns = [f'col_{i}' for i in range(df.shape[1])]
    
    # FIX: Parse the true publication date from the filename (e.g., price_report_20260617.pdf)
    filename = os.path.basename(pdf_path)
    date_match = re.search(r'price_report_(\d{8})', filename)
    
    if date_match:
        raw_date_str = date_match.group(1)
        # Reformat from YYYYMMDD to YYYY-MM-DD
        report_date = datetime.strptime(raw_date_str, "%Y%m%d").strftime("%Y-%m-%d")
    else:
        # Fallback if filename structure changes
        report_date = datetime.now().strftime("%Y-%m-%d")
        logging.warning(f"Could not extract date from filename '{filename}'. Falling back to system date.")
        
    df['report_date'] = report_date
    return df

def parse_pdf_to_csv(pdf_path, output_csv):
    df = parse_cbsl_pdf(pdf_path)

    # Check if file exists and is not empty
    if os.path.exists(output_csv) and os.path.getsize(output_csv) > 0:
        master = pd.read_csv(output_csv)
        # Avoid duplicates: check if same date already present
        if not master[master['report_date'] == df['report_date'].iloc[0]].empty:
            logging.info(f"Data for {df['report_date'].iloc[0]} already exists in raw CSV. Skipping.")
            return
        master = pd.concat([master, df], ignore_index=True)
    else:
        master = df

    master.to_csv(output_csv, index=False)
    logging.info(f"Appended raw data to {output_csv}")
