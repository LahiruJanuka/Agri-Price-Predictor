"""
This module cleans raw market data and prepares historical features.
It takes a wide table and converts it into a clean, long time-series format.
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import os
from .utils import ensure_dir, setup_logging


KNOWN_CATEGORIES = ['VEGETABLES', 'OTHER', 'FRUITS', 'RICE', 'FISH']


def get_column_matrix(category):
    """
    Returns the market column mapping matching CBSL Daily Price Report layout.
    - VEGETABLES / OTHER / FRUITS:
        Wholesale: Pettah (cols 2,3), Dambulla (cols 4,5)
        Retail: Pettah (cols 6,7), Dambulla (cols 8,9), Narahenpita (cols 10,11)
    - RICE:
        Wholesale: Pettah (cols 2,3), Marandagahamula (cols 4,5)
        Retail: Pettah (cols 6,7), Dambulla (cols 8,9), Narahenpita (cols 10,11)
    - FISH:
        Wholesale: Peliyagoda (cols 2,3), Negombo (cols 4,5)
        Retail: Negombo (cols 8,9), Narahenpita (cols 10,11)
    """
    cat = category.upper()
    if cat == "FISH":
        return [
            {"col_idx": 2, "market": "Peliyagoda", "price_type": "Wholesale", "is_today": False},
            {"col_idx": 3, "market": "Peliyagoda", "price_type": "Wholesale", "is_today": True},
            {"col_idx": 4, "market": "Negombo",    "price_type": "Wholesale", "is_today": False},
            {"col_idx": 5, "market": "Negombo",    "price_type": "Wholesale", "is_today": True},
            {"col_idx": 8, "market": "Negombo",    "price_type": "Retail",    "is_today": False},
            {"col_idx": 9, "market": "Negombo",    "price_type": "Retail",    "is_today": True},
            {"col_idx": 10, "market": "Narahenpita", "price_type": "Retail",   "is_today": False},
            {"col_idx": 11, "market": "Narahenpita", "price_type": "Retail",   "is_today": True},
        ]
    elif cat == "RICE":
        return [
            {"col_idx": 2, "market": "Pettah",          "price_type": "Wholesale", "is_today": False},
            {"col_idx": 3, "market": "Pettah",          "price_type": "Wholesale", "is_today": True},
            {"col_idx": 4, "market": "Marandagahamula", "price_type": "Wholesale", "is_today": False},
            {"col_idx": 5, "market": "Marandagahamula", "price_type": "Wholesale", "is_today": True},
            {"col_idx": 6, "market": "Pettah",          "price_type": "Retail",    "is_today": False},
            {"col_idx": 7, "market": "Pettah",          "price_type": "Retail",    "is_today": True},
            {"col_idx": 8, "market": "Dambulla",        "price_type": "Retail",    "is_today": False},
            {"col_idx": 9, "market": "Dambulla",        "price_type": "Retail",    "is_today": True},
            {"col_idx": 10, "market": "Narahenpita",    "price_type": "Retail",    "is_today": False},
            {"col_idx": 11, "market": "Narahenpita",    "price_type": "Retail",    "is_today": True},
        ]
    else:  # VEGETABLES, OTHER, FRUITS, and general commodities
        return [
            {"col_idx": 2, "market": "Pettah",      "price_type": "Wholesale", "is_today": False},
            {"col_idx": 3, "market": "Pettah",      "price_type": "Wholesale", "is_today": True},
            {"col_idx": 4, "market": "Dambulla",    "price_type": "Wholesale", "is_today": False},
            {"col_idx": 5, "market": "Dambulla",    "price_type": "Wholesale", "is_today": True},
            {"col_idx": 6, "market": "Pettah",      "price_type": "Retail",    "is_today": False},
            {"col_idx": 7, "market": "Pettah",      "price_type": "Retail",    "is_today": True},
            {"col_idx": 8, "market": "Dambulla",    "price_type": "Retail",    "is_today": False},
            {"col_idx": 9, "market": "Dambulla",    "price_type": "Retail",    "is_today": True},
            {"col_idx": 10, "market": "Narahenpita","price_type": "Retail",    "is_today": False},
            {"col_idx": 11, "market": "Narahenpita","price_type": "Retail",    "is_today": True},
        ]


def clean_raw_data(raw_df):
    """
    Goes through the raw CSV row by row, looks at each market column,
    and reorganizes the layout into individual rows for each price record.
    Preserves exact individual markets (Pettah, Dambulla, Narahenpita, Peliyagoda,
    Negombo, Marandagahamula) per the CBSL reports.
    """
    records = []
    current_category = "GENERAL"

    for idx, row in raw_df.iterrows():
        # Detect category header anywhere across row cells
        for val in row.values:
            if pd.notna(val):
                compact = "".join(str(val).split()).upper()
                if compact in KNOWN_CATEGORIES:
                    current_category = compact
                    logging.info(f"Changed tracking category to: {current_category}")
                    break

        # Get item name, units, and report date from the row
        item = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        unit = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        report_date_str = row.get('report_date')

        # Skip rows that don't have a valid date string
        if not report_date_str or pd.isna(report_date_str):
            continue

        try:
            report_date = datetime.strptime(str(report_date_str), "%Y-%m-%d")
        except ValueError:
            continue

        # Commodity data rows must have valid item name and valid unit (e.g. Rs./kg)
        if not item or item.lower() in ['item', 'unit', 'nan', ''] or item.startswith('n.a.'):
            continue
        if not unit or unit.lower() in ['nan', ''] or not unit.lower().startswith('rs.'):
            continue

        # Get category-specific column matrix
        column_matrix = get_column_matrix(current_category)

        # Extract price from each column specified in the matrix
        for mapping in column_matrix:
            if mapping["col_idx"] >= len(row):
                continue

            raw_val = str(row.iloc[mapping["col_idx"]]).strip().lower()
            
            # Skip empty entries, dots, or "n.a." labels safely
            if raw_val in ['n.a.', 'na', '', 'nan', 'none', '.']:
                continue

            try:
                price_float = float(raw_val.replace(',', ''))
            except ValueError:
                continue

            # Assign the correct date to the entry
            if mapping["is_today"]:
                target_date = report_date
            else:
                target_date = report_date - timedelta(days=1)

            records.append({
                'date': target_date.strftime("%Y-%m-%d"),
                'category': current_category,
                'item': item,
                'unit': unit,
                'market': mapping["market"],
                'price_type': mapping["price_type"],
                'price': price_float
            })

    long_df = pd.DataFrame(records)
    if not long_df.empty:
        long_df.drop_duplicates(subset=['date', 'item', 'market', 'price_type'], inplace=True)
        long_df['date'] = pd.to_datetime(long_df['date'])
        
    return long_df


def aggregate_and_compute_features(long_df):
    """
    Sorts data in order and computes basic time-series values:
    Yesterday's Price, 7-Day Average, and Price Change.
    """
    if long_df.empty:
        return long_df

    # Sort data chronologically so we can calculate shifts and averages safely
    df = long_df.sort_values(['category', 'item', 'market', 'price_type', 'date']).reset_index(drop=True)
    
    # 1. Yesterday's Price: Shifts data down by 1 position within each group
    df['yesterday_price'] = df.groupby(['category', 'item', 'market', 'price_type'])['price'].shift(1)
    
    # 2. Rolling Week Average: Looks at previous 7 items to calculate mean average
    df['week_avg'] = df.groupby(['category', 'item', 'market', 'price_type'])['price'].rolling(7, min_periods=1).mean().reset_index(level=[0,1,2,3], drop=True)
    
    # 3. Daily Price Change: Subtract yesterday's price from today's price
    df['daily_change'] = df['price'] - df['yesterday_price']
    
    return df


def run_data_cleaning_pipeline(raw_csv_path, output_csv_path):
    """
    Main manager function that coordinates the cleaner.
    It reads raw data, combines it with old history without erasing it, and saves it.
    """
    logging.info("Starting historical data cleaner pipeline...")
    
    if not os.path.exists(raw_csv_path):
        raise FileNotFoundError(f"Raw CSV data file not found at: {raw_csv_path}")
        
    raw_df = pd.read_csv(raw_csv_path)
    
    # Clean and unpack the columns from the raw scraper data
    new_data = clean_raw_data(raw_df)
    if new_data.empty:
        logging.warning("No new data was found to clean.")
        return None
        
    # Check if a history file already exists on our computer
    if os.path.exists(output_csv_path) and os.path.getsize(output_csv_path) > 0:
        logging.info("History file found. Merging data fields...")
        old_history = pd.read_csv(output_csv_path)
        old_history['date'] = pd.to_datetime(old_history['date'])
        
        # Prune legacy combined market names if present
        if 'market' in old_history.columns:
            old_history = old_history[~old_history['market'].str.contains('/', na=False)]
        
        # Look at the list of dates we just extracted today
        incoming_dates = new_data['date'].unique()
        
        # Simple loop filter: Keep rows from history only if they do not match incoming dates
        # This deletes old records for today/yesterday before appending new ones (no duplicates)
        old_history = old_history[~old_history['date'].isin(incoming_dates)]
        
        # Glue the cleaned old history rows and new rows together
        combined_data = pd.concat([old_history, new_data], ignore_index=True)
    else:
        logging.info("No prior history found. Initializing new history file.")
        combined_data = new_data

    # Re-calculate moving features across the entire historical timeline
    final_output_df = aggregate_and_compute_features(combined_data)
    
    # Save the accumulated table back to the folder location
    ensure_dir(os.path.dirname(output_csv_path))
    final_output_df.to_csv(output_csv_path, index=False)
    logging.info(f"Successfully saved and accumulated data into: {output_csv_path}")
    
    return final_output_df


if __name__ == "__main__":
    setup_logging()
    raw_csv = "data/processed/cbsl_prices_raw.csv"
    output_csv = "data/processed/crop_history.csv"
    run_data_cleaning_pipeline(raw_csv, output_csv)
