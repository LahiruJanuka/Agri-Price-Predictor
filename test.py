"""
Updated script to test the multi-market LangGraph workflow.
"""
from src.workflow import predict_crop_price
import logging

def run_test():
    print("=" * 60)
    print("STARTING MULTI-AGENT MULTI-MARKET PRICE PREDICTION TEST")
    print("=" * 60)

    # 1. Configure the explicit market channel you want to test
    # Options for market: "Pettah/Peliyagoda", "Dambulla/Negombo"
    # Options for price_type: "Wholesale", "Retail"
    target_crop = "Brinjal"
    target_market = "Dambulla/Negombo"
    target_price_type = "Wholesale"

    print(f"Targeting: {target_crop} | {target_market} ({target_price_type})")
    print("Running pipeline...\n")

    # 2. Trigger the workflow with the updated multi-market signature
    result = predict_crop_price(
        crop=target_crop, 
        market=target_market, 
        price_type=target_price_type
    )

    # 3. Check for pipeline error traps
    if result.get("error"):
        print(f"❌ PIPELINE FAILED!")
        print(f"Error Message: {result['error']}")
        print("=" * 60)
        return

    # 4. Print clean structured state results
    print(f"✅ PIPELINE SUCCEEDED!")
    print("-" * 50)
    print(f"Crop Analyzed:    {result.get('crop')}")
    print(f"Market Hub:       {result.get('market')}")
    print(f"Pricing Channel:  {result.get('price_type')}")
    print("-" * 50)
    print(f"Latest Price:     {result.get('current_price')} LKR/kg")
    print(f"Yesterday Price:  {result.get('yesterday_price')} LKR/kg")
    print(f"7-Day Moving Avg: {result.get('week_avg')} LKR/kg")
    print(f"Trend Direction:  {result.get('trend').upper()}")
    print(f"Recent Window:    {result.get('recent_prices')}")
    print("-" * 50)
    print(f"🔮 AI TOMORROW PREDICTION: {result.get('prediction')} LKR/kg")
    print(f"💡 REASONING EXPLANATION:  {result.get('recommendation')}")
    print("=" * 60)

if __name__ == "__main__":
    # Setup simple logging to see the Agent actions in the terminal
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_test()
