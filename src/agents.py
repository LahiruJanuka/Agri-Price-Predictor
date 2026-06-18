"""
LangGraph agent functions for data loading, trend analysis, and prediction.
Uses LangChain Groq to connect to high-speed cloud LLMs.
"""

import os
import pandas as pd
import logging
from typing import TypedDict, Any, Dict
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pandas.io.parsers.readers import csv
from .prompts import PRICE_PREDICTION_PROMPT

# Load the environment variables from the .env file
load_dotenv()

#---------------------
# Agent 1: Data Loader
#---------------------
def load_data(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reads the historical crop ledger file and filters rows for the 
    requested crop, specific market, and pricing channel type.
    """
    crop = state.get("crop")
    # Get the market and price type from state, or default to Pettah Wholesale if missing
    market = state.get("market", "Pettah/Peliyagoda")
    price_type = state.get("price_type", "Wholesale")

    if not crop:
        state["error"] = "No crop item was specified."
        return state

    # Points directly to your true data pipeline master ledger path
    csv_path = "data/processed/crop_history.csv"
    
    try:
        if not os.path.exists(csv_path):
            state["error"] = f"Database file not found at: {csv_path}"
            return state

        df = pd.read_csv(csv_path)
        df['date'] = pd.to_datetime(df['date'])
        
        # FIX: Filter rows by match-matching item, market, and price type together
        df = df[
            (df['item'].str.lower() == crop.lower()) & 
            (df['market'].str.lower() == market.lower()) & 
            (df['price_type'].str.lower() == price_type.lower())
        ].copy()
        
        if df.empty:
            state["error"] = f"No data found for {crop} at {market} ({price_type})"
            return state
            
        # Sort sequentially by date and keep the latest 30 rows for this market stream
        df.sort_values('date', inplace=True)
        df = df.tail(30).reset_index(drop=True)
        
        state["historical_data"] = df
        state["error"] = None
        logging.info(f"Loaded {len(df)} rows for {crop} at {market} ({price_type})")
        
    except Exception as e:
        state["error"] = f"Data loader failed: {str(e)}"
        logging.error(state["error"])
        
    return state
#------------------------
# Agent 2: Trend Analyzer
#------------------------

def analyze_trend(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extracts the latest metrics from out data table to build mathematical context
    """
    df = state.get("historical_data")
    if df is None or df.empty:
        state["error"] = "No history dataframe found to analyze"
        return state

    # Grab the very last row (recent market day)
    latest_row = df.iloc[-1]
    
    current_price = float(latest_row['price'])
    yesterday_price = latest_row.get('yesterday_price', current_price)
    week_avg = latest_row.get('week_avg', current_price)
    daily_change = latest_row.get('daily_change', 0)

    # Get a plain list of the last 7 sequencial prices
    recent_prices = df['price'].tail(7).tolist()

    # Determine trend status direction
    if daily_change > 0:
        trend = "upward"
    elif daily_change < 0:
        trend = "downward"
    else:
        trend = "stable"

    # Save calculated trend metrics back to the shared graph state dictionary
    state["current_price"] = current_price
    state["yesterday_price"] = yesterday_price
    state["week_avg"] = week_avg
    state["daily_change"] = daily_change
    state["trend"] = trend
    state["recent_prices"] = recent_prices
    state["error"] = None

    logging.info(f"Analyzed {state['crop']}: price={current_price}, Trend={trend}")
    return state


#-------------------
# Agent 3: Predictor
#-------------------

def predict_price(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends data context to Groq's openai/gpt-oss-120b model to forecast tommorow's crop price.
    """

    crop = state.get("crop")
    recent_prices = state.get("recent_prices", [])
    week_avg = state.get("week_avg", 0)
    fallback_baseline = state.get("current_price", 0)

    if not recent_prices:
        state["error"] = "No recent price data available for prediction."
        state["prediction"] = fallback_baseline
        state["recommendation"] = "Using current price baseline due to missing data."
        return state

    # Format the array list of past prices into clean text bullet points
    price_history_text = "\n".join([f"- {p:.2f} LKR" for p in recent_prices])

    # Inject variables directly into prompt string layout
    prompt_message = PRICE_PREDICTION_PROMPT.format(
        crop = crop,
        price_history = price_history_text,
        week_avg = float(week_avg)
    )

    try:
        # Check if API key is loaded before trying to trigger the cloud model
        if not os.getenv("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY is missing from environment. Check your .env file.")

        # Initialize ChatGroq
        llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.2)
        
        # Invoke the cloud model
        response = llm.invoke(prompt_message)
        raw_output_text = response.content

        # Parse out the prediction numbers using a simple string search
        import re
        pred_match = re.search(r"PREDICTION:\s*([\d.]+)", raw_output_text, re.IGNORECASE)
        reason_match = re.search(r"REASON:\s*(.*)", raw_output_text, re.IGNORECASE)

        if pred_match:
            prediction_value = float(pred_match.group(1))
        else:
            prediction_value = float(week_avg) # Fallback to 7-day average if parser fails
            logging.warning("Could not parse prediction number text. Defaulting to week average.")

        reason_text = reason_match.group(1).strip() if reason_match else "No explanation provided."

        # Commit final answers back to graph state
        state["prediction"] = prediction_value
        state["recommendation"] = reason_text
        state["error"] = None
        logging.info(f"Groq Advisor Prediction for {crop}: {prediction_value} LKR")

    except Exception as e:
        state["error"] = f"Groq Cloud connection failed: {str(e)}"
        state["prediction"] = float(week_avg)
        state["recommendation"] = "Using week moving average fallback due to system connection error."
        logging.error(state["error"])

    return state 









