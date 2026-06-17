import camelot
import pandas as pd
import re
import logging
from datetime import datetime
import os

def parse_cbsl_pdf(pdf_path):
    """
    Extract the price table from CBSL PDF (page 2) and return a cleaned DataFrame.
    The table has a complex multi-level header.
    We'll extract using camelot with lattice flavor.
    """

    # Read table from page 2
    tables = camelot.read_pdf(pdf_path, pages='2', flavor='lattice')
    if not tables:
        raise Exception("No tables found in PDF page 2.")

    df = tables[0].df # Extract as pandas DataFrame of strings

    # Clean: drop first two rows (header info) and last empty rows if any
    df = df.iloc[2:].reset_index(drop=True)

    # The first column is the item name, second is unit, etc.
    # We need to map columns to proper names.
    # Based on the example, the columns order (after dropping header rows):
    # Col0: Item
    # Col1: Unit
    # Col2-5: Wholesale Petah Yesterday/Today, Wholesale Dambulla Yesterday/Today
    # Col6-9: Retail Petah Yesterday/Today, Retail Dambulla Yesterday/Today
    # ... but the PDF has more columns for other items (Fish, Rice, Fruits) with varying market columns.
    # To keep it simple, we'll parse the table as is and then restructure.
    
    # Let's take the first 10 columns which correspond to vegetables (the main part)
    # But we want all items. The PDF has many columns. We'll rename columns generically.
    
    # For simplicity, we extract the entire table and then manually assign column names
    # based on the header rows we dropped.
    # A more robust approach: extract the header from row 1 and 2, but we'll hardcode column names
    # for known structure: 
    # Columns: Item, Unit, 
    # Petah Wholesale Yesterday, Petah Wholesale Today,
    # Dambulla Wholesale Yesterday, Dambulla Wholesale Today,
    # Petah Retail Yesterday, Petah Retail Today,
    # Dambulla Retail Yesterday, Dambulla Retail Today,
    # then additional columns for other items (coconut, rice, fish) with their own markets.
    # To keep it generic, we'll output all columns with generic names.
    
    # For simplicity, we'll just rename columns as 'col_0', 'col_1', ...
    # Then we'll reshape into long format.

    df.columns = [f'col_{i}' for i in range(df.shape[1])]
    
    # Add a date column based in today's date 
    report_date = datetime.now().strftime("%Y-%m-%d")
    df['report_date'] = report_date

    # Later reshape to long format (item, unit, market, price_type, price)
    return df

def parse_pdf_to_csv(pdf_path, output_csv):
    df = parse_cbsl_pdf(pdf_path)
    # Append to master CSV (if exist)

    if os.path.exists(output_csv):
        master = pd.read_csv(output_csv)
        # Avoid duplicates: check if same date already present
        if not master[master['report_date'] == df['report_date'].iloc[0]].empty:
            logging.info(f"Data for {df['report_date'].iloc[0]} already exists. Skipping.")
            return
        master = pd.concat([master, df], ignore_index=True)

    else:
        master = df

    master.to_csv(output_csv, index=False)
    logging.info(f"Append data to {output_csv}")
