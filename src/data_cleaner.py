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


def clean_raw_data(raw_df):
    """
    Goes through the raw CSV row by row, looks at each market column,
    and reorganizes the layout into individual rows for each price record.
    """
    records = []
    current_category = "GENERAL"  # Starts with a default food category

    for idx, row in raw_df.iterrows():
        # Get item name, units, and report date from the row
        item = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        unit = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        report_date_str = row.get('report_date')

        # Skip rows that don't have a valid date string
        if not report_date_str or pd.isna(report_date_str):
            continue

        try:
            # Convert text date to a real Python datetime object
            report_date = datetime.strptime(str(report_date_str), "%Y-%m-%d")
        except ValueError:
            continue

        # Skip rows that are just empty text or basic column names
        if item.lower() in ['item', 'unit', 'nan', ''] and not unit:
            continue

        # CATEGORY DETECTOR: If item has text but unit is completely empty,
        # it means we hit a section title row (like "VEGETABLES" or "FRUITS")
        if item and (not unit or unit.lower() in ['nan', '']):
            # Make sure it isn't a random header row text
            if not any(header in item.lower() for header in ['price', 'wholesale', 'retail', 'selected']):
                current_category = item.upper().replace(" ", "")
                logging.info(f"Changed tracking category to: {current_category}")
            continue

        # COLUMN INDEX DICTIONARY LIST
        # Tells the computer exactly which column index represents what market information
        column_matrix = [
            {"col_idx": 2, "market": "Pettah/Peliyagoda", "price_type": "Wholesale", "is_today": False}, # Yesterday Price
            {"col_idx": 3, "market": "Pettah/Peliyagoda", "price_type": "Wholesale", "is_today": True},  # Today Price
            {"col_idx": 4, "market": "Dambulla/Negombo",  "price_type": "Wholesale", "is_today": False}, # Yesterday Price
            {"col_idx": 5, "market": "Dambulla/Negombo",  "price_type": "Wholesale", "is_today": True},  # Today Price
            {"col_idx": 6, "market": "Pettah/Peliyagoda", "price_type": "Retail",    "is_today": False}, # Yesterday Price
            {"col_idx": 7, "market": "Pettah/Peliyagoda", "price_type": "Retail",    "is_today": True},  # Today Price
            {"col_idx": 8, "market": "Dambulla/Negombo",  "price_type": "Retail",    "is_today": False}, # Yesterday Price
            {"col_idx": 9, "market": "Dambulla/Negombo",  "price_type": "Retail",    "is_today": True}   # Today Price
        ]

        # Extract price from each column specified in the list above
        for mapping in column_matrix:
            # Avoid crashes if the row somehow has fewer columns than expected
            if mapping["col_idx"] >= len(row):
                continue

            raw_val = str(row.iloc[mapping["col_idx"]]).strip().lower()
            
            # Skip empty entries or "N.A." labels safely
            if raw_val in ['n.a.', 'na', '', 'nan']:
                continue

            try:
                # Remove any commas from text numbers and turn into a float decimal
                price_float = float(raw_val.replace(',', ''))
            except ValueError:
                continue

            # Assign the correct date to the entry
            if mapping["is_today"] == True:
                target_date = report_date
            else:
                # Subtract 1 day if this column belongs to yesterday's data
                target_date = report_date - timedelta(days=1)

            # Build a simple dictionary record for this price data point
            records.append({
                'date': target_date.strftime("%Y-%m-%d"),
                'category': current_category,
                'item': item,
                'unit': unit,
                'market': mapping["market"],
                'price_type': mapping["price_type"],
                'price': price_float
            })

    # Convert our list of dictionaries into a clean structured table
    long_df = pd.DataFrame(records)
    if not long_df.empty:
        # Drop identical duplicate entries to keep data honest
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
