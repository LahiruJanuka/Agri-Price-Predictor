"""
LangGraph agent functions for data loading, trend analysis, and prediction.
Uses LangChain Groq to connect to high-speed cloud LLMs.
"""

import os
import pandas as pd
import numpy as np
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
    Extracts moving averages, directional momentum, and statistical trend indicators
    from historical data to provide grounded math contexts for the LLM.
    """
    df = state.get("historical_data")
    if df is None or df.empty or len(df) < 2:
        state["error"] = "Insufficient historical data points to execute mathematical trend analysis"
        state["trend"] = "unknown"
        return state

    # 1. Ensure chronological order (Crucial for time-series parsing)
    df = df.sort_values(by="date").copy()

    # 2. Extract price arrays and verify sizing
    prices = df['price'].astype(float).tolist()
    recent_prices = prices[-7:]  # Capture last 7 data entries for UI tracking
    
    current_price = prices[-1]
    yesterday_price = prices[-2]
    daily_change = current_price - yesterday_price

    # 7-day Simple Moving Average (SMA) handles noise dampening
    window_7d = prices[-7:]
    week_avg = float(np.mean(window_7d))
    
    # 7-Day Momentum: How much did the price move compared to 7 market days ago?
    historical_reference_idx = -7 if len(prices) >= 7 else -len(prices)
    price_7_days_ago = prices[historical_reference_idx]
    seven_day_change_pct = ((current_price - price_7_days_ago) / price_7_days_ago) * 100

    # 4. Introduce a Dynamic Stability Threshold (Noise Gate)
    # Agricultural commodities bounce around daily. If a movement is under 2%, 
    NOISE_THRESHOLD_PCT = 2.0 

    if seven_day_change_pct > NOISE_THRESHOLD_PCT:
        trend = "upward"
    elif seven_day_change_pct < -NOISE_THRESHOLD_PCT:
        trend = "downward"
    else:
        trend = "stable"

    # 5. Advanced Signal: Position Relative to Moving Average
    # Is the price accelerating above average or breaking down below average?
    ma_deviation_pct = ((current_price - week_avg) / week_avg) * 100

    # 6. Hydrate the Graph State Context Dictionary
    state["current_price"] = current_price
    state["yesterday_price"] = yesterday_price
    state["week_avg"] = week_avg
    state["daily_change"] = daily_change
    state["seven_day_change_pct"] = round(seven_day_change_pct, 2)
    state["ma_deviation_pct"] = round(ma_deviation_pct, 2)
    state["trend"] = trend
    state["recent_prices"] = recent_prices
    state["error"] = None

    logging.info(
        f"📊 Logic Engine [{state.get('crop', 'Crop')}]: "
        f"Price={current_price} LKR | 7D-Move={seven_day_change_pct:.1f}% | Trend={trend.upper()}"
    )
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
    seven_day_change = state.get("seven_day_change_pct", 0.0)
    ma_deviation = state.get("ma_deviation_pct", 0.0)
    trend = state.get("trend", "stable")
    
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
        week_avg = float(week_avg),
        seven_day_change=float(seven_day_change),
        ma_deviation=float(ma_deviation),
        trend=trend.upper()
    )

    try:
        # Check if API key is loaded before trying to trigger the cloud model
        if not os.getenv("GROQ_API_KEY"):
            raise ValueError("GROQ_API_KEY is missing from environment. Check your .env file.")

        # Initialize ChatGroq
        llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0.1)
        
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









