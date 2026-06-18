"""
Prompt templates for the predictor agent.
"""

PRICE_PREDICTION_PROMPT = """
You are an expert crop price forecasting advisor for Sri Lankan agricultural markets. 
Analyze the following historical data matrix and technical indicators for {crop} (in LKR per kg):

=== HISTORICAL PRICE SEQUENCE (Last 7 Days) ===
{price_history}

=== STATISTICAL COMMODITY INDICATORS ===
- 7-Day Simple Moving Average (SMA): {week_avg:.2f} LKR/kg
- 7-Day Macro Momentum Velocity: {seven_day_change:+.2f}%
- Position Relative to Moving Average: {ma_deviation:+.2f}%
- Evaluated Market Baseline Trend: {trend}

Your Task:
Predict tomorrow's wholesale price for {crop}. Evaluate whether minor daily shifts are just short-term market noise or aligning with the macro momentum vector ({seven_day_change}%). 

You must output your final answer using the exact template blocks below. Do not include conversational greetings, introductions, or markdown bolding inside the tags.

FORMAT TEMPLATE:
PREDICTION: <Write only the final calculated numeric price here, e.g., 185.50>
REASON: <Provide a one-sentence agricultural or trend-based explanation here>
"""
