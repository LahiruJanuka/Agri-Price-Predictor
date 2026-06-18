"""
Assemble the LangGraph multi-agent workflow.
Manages state memory and pipeline routing paths.
"""

from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional, List, Dict, Any
import pandas as pd
from .agents import load_data, analyze_trend, predict_price

# Define the shared memory graph state schema
class PredictionState(TypedDict):
    crop: str
    market: str
    price_type: str
    historical_data: Optional[pd.DataFrame]
    current_price: Optional[float]
    yesterday_price: Optional[float]
    week_avg: Optional[float]
    daily_change: Optional[float]
    trend: Optional[str]
    recent_prices: Optional[List[float]]
    prediction: Optional[float]
    recommendation: Optional[str]
    error: Optional[str]

# Gatekeeper Routing Function
def route_after_node(state: PredictionState) -> str:
    """
    Traffic cop logic. If an error is spotted in the state dictionary, 
    it terminates the graph immediately instead of passing bad data forward.
    """
    if state.get("error") is not None:
        return "exit_pipeline"
    return "continue_pipeline"

# Build and Compile the graph
def build_workflow():
    # Initialize the graph
    workflow = StateGraph(PredictionState)

    # 1. Register Agent Nodes
    workflow.add_node("load_data", load_data)
    workflow.add_node("analyze_trend", analyze_trend)
    workflow.add_node("predict_price", predict_price)

    # 2. Establish entry point
    workflow.set_entry_point("load_data")

    # 3. Add conditional Routes to check for errors before running next Nodes
    workflow.add_conditional_edges(
        "load_data",
        route_after_node,
        {
            "continue_pipeline": "analyze_trend",
            "exit_pipeline": END
        }
    )

    workflow.add_conditional_edges(
        "analyze_trend",
        route_after_node,
        {
            "continue_pipeline": "predict_price",
            "exit_pipeline": END
        }
    )

    # Final prediction agent naturally sends data directly to the END
    workflow.add_edge("predict_price", END)


    return workflow.compile()


# App Execution Wrapper Function
def predict_crop_price(crop: str, market: str = "Pettah/Peliyagoda", price_type: str = "Wholesale") -> Dict[str, Any]:
    """
    Run the full compiled workflow for a given crop and return the final state dictionary.
    """
    app = build_workflow()

    initial_state: PredictionState = {
        "crop": crop,
        "market": market,
        "price_type": price_type,
        "historical_data": None,
        "current_price": None,
        "yesterday_price": None,
        "week_avg": None,
        "daily_change": None,
        "trend": None,
        "recent_prices": None,
        "prediction": None,
        "recommendation": None,
        "error": None
    }

    # Run the application
    result = app.invoke(initial_state)
    return result






