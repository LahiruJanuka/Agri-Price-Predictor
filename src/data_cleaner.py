"""
Data Cleaning & Feature Engineering Module
Transforms wide raw parsed CSV columns into a long time-series format,
correctly mapping dedicated columns to explicit prices.
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import os
from .utils import ensure_dir, setup_logging

def clean_raw_data(raw_df):
    """
    Processes all items across the raw CSV by mapping explicit column index ranges
    to their true market definitions.
    """
    records = []
    current_category = "GENERAL"  # Fallback tracker

    for idx, row in raw_df.iterrows():
        # Clean text tokens from descriptive base columns
        item = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        unit = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        report_date_str = row.get('report_date')

        if not report_date_str or pd.isna(report_date_str):
            continue

        try:
            report_date = datetime.strptime(str(report_date_str), "%Y-%m-%d")
        except ValueError:
            continue

        # Skip layout rows or structural table metadata headers
        if item.lower() in ['item', 'unit', 'nan', ''] and not unit:
            continue

        # DYNAMIC SECTION DETECTOR:
        # If item has text but unit is blank, it marks a major section banner
        # (e.g., 'VEGETABLES', 'FRUITS', 'RICE', 'FISH')
        if item and (not unit or unit.lower() in ['nan', '']):
            if not any(header in item.lower() for header in ['price', 'wholesale', 'retail', 'selected']):
                current_category = item.upper().replace(" ", "")
                logging.info(f"Switched data pipeline parsing scope to context: {current_category}")
            continue

        # DIRECT COLUMN INDEX MAPPING MATRIX
        # Matches your exact cbsl_prices_raw.csv output layout
        column_matrix = [
            {"col_idx": 2, "market": "Pettah/Peliyagoda", "price_type": "Wholesale", "is_today": False}, # Yesterday
            {"col_idx": 3, "market": "Pettah/Peliyagoda", "price_type": "Wholesale", "is_today": True},  # Today
            {"col_idx": 4, "market": "Dambulla/Negombo", "price_type": "Wholesale", "is_today": False}, # Yesterday
            {"col_idx": 5, "market": "Dambulla/Negombo", "price_type": "Wholesale", "is_today": True},  # Today
            {"col_idx": 6, "market": "Pettah/Peliyagoda", "price_type": "Retail",    "is_today": False}, # Yesterday
            {"col_idx": 7, "market": "Pettah/Peliyagoda", "price_type": "Retail",    "is_today": True},  # Today
            {"col_idx": 8, "market": "Dambulla/Negombo", "price_type": "Retail",    "is_today": False}, # Yesterday
            {"col_idx": 9, "market": "Dambulla/Negombo", "price_type": "Retail",    "is_today": True}   # Today
        ]

        for mapping in column_matrix:
            if mapping["col_idx"] >= len(row):
                continue

            raw_val = str(row.iloc[mapping["col_idx"]]).strip().lower()
            
            # Skip empty, missing, or non-available entries safely
            if raw_val in ['n.a.', 'na', '', 'nan']:
                continue

            try:
                # Clean up numeric formatting punctuation
                price_float = float(raw_val.replace(',', ''))
            except ValueError:
                continue

            # FIX: Dynamically shift the database date stamp backward for historical columns
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
    Computes time-series lag variables and windows grouped across unique items.
    """
    if long_df.empty:
        return long_df

    # Sort sequentially to preserve rolling window metrics
    df = long_df.sort_values(['category', 'item', 'market', 'price_type', 'date']).reset_index(drop=True)
    
    # Yesterday's price relative to its specific market row tracking series
    df['yesterday_price'] = df.groupby(['category', 'item', 'market', 'price_type'])['price'].shift(1)
    
    # 7-Day Simple Moving Average
    df['week_avg'] = df.groupby(['category', 'item', 'market', 'price_type'])['price'].transform(
        lambda x: x.rolling(7, min_periods=1).mean()
    )
    
    # Absolute daily price delta change
    df['daily_change'] = df['price'] - df['yesterday_price']
    
    return df

def run_data_cleaning_pipeline(raw_csv_path, output_csv_path):
    """Main sequence cleaner pipeline orchestrator."""
    logging.info("Initializing explicit-column cleaning transformation...")
    
    if not os.path.exists(raw_csv_path):
        raise FileNotFoundError(f"Raw data link target missing at: {raw_csv_path}")
        
    raw_df = pd.read_csv(raw_csv_path)
    
    # Clean and unpack columns
    long_df = clean_raw_data(raw_df)
    logging.info(f"Unpacked {len(long_df)} clean long-format record nodes.")
    
    # Compute time-series features
    feature_df = aggregate_and_compute_features(long_df)
    
    ensure_dir(os.path.dirname(output_csv_path))
    feature_df.to_csv(output_csv_path, index=False)
    logging.info(f"Master commodity history ledger safely saved to: {output_csv_path}")
    
    return feature_df

if __name__ == "__main__":
    setup_logging()
    raw_csv = "data/processed/cbsl_prices_raw.csv"
    output_csv = "data/processed/crop_history.csv"
    run_data_cleaning_pipeline(raw_csv, output_csv)
