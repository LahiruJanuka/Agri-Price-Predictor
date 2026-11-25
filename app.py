import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import os
from src.workflow import predict_crop_price

# ----------------------------------------------------------------------
# Page Configurations & Theme Setting
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Govi Gnana Price Predictor", 
    page_icon="🌾", 
    layout="wide", 
    initial_sidebar_state="expanded"
)

# Dark Mode-safe CSS styling using Streamlit native theme variables
st.markdown("""
    <style>
    /* Earthy green heading */
    .main-title { color: #2e7d32; font-family: 'Georgia', serif; font-weight: bold; }
    
    /* Adaptable container elements using system-aware secondary backgrounds */
    .farmer-box { 
        background-color: rgba(76, 175, 80, 0.1); 
        border-left: 5px solid #4caf50; 
        padding: 15px; 
        border-radius: 5px;
        color: inherit;
    }
    .disclaimer-box { 
        background-color: rgba(255, 152, 0, 0.1); 
        border-left: 5px solid #ff9800; 
        padding: 12px; 
        border-radius: 5px; 
        font-size: 0.9em; 
        color: inherit;
    }
    </style>
""", unsafe_allow_html=True)

# CSV Database File Configuration Path
DATA_PATH = "data/processed/crop_history.csv"

# ----------------------------------------------------------------------
# Cache Loading Functions (Optimizes Speed)
# ----------------------------------------------------------------------
@st.cache_data
def load_master_data():
    """Reads master file to provide dynamic choices and records."""
    if not os.path.exists(DATA_PATH):
        return pd.DataFrame()
    df = pd.read_csv(DATA_PATH)
    df['date'] = pd.to_datetime(df['date'])
    return df

df_master = load_master_data()

# ----------------------------------------------------------------------
# Sidebar Controls (Dynamic Searchable Options)
# ----------------------------------------------------------------------
st.sidebar.markdown("<h2 style='color:#2e7d32;'>🌾 Govi Control Panel</h2>", unsafe_allow_html=True)
st.sidebar.write("Configure your commodity and market filter choices below:")

if not df_master.empty:
    available_crops = sorted(df_master['item'].dropna().unique())
    selected_crop = st.sidebar.selectbox("🔎 Search or Select Commodity / Crop", available_crops)

    # Filter markets available specifically for the selected commodity
    crop_df = df_master[df_master['item'].str.lower() == selected_crop.lower()]
    crop_category = crop_df['category'].iloc[0] if ('category' in crop_df.columns and not crop_df.empty) else ""
    if crop_category:
        st.sidebar.caption(f"📂 **Category:** {crop_category}")

    available_markets = sorted(crop_df['market'].dropna().unique())
    selected_market = st.sidebar.selectbox("📍 Market Location", available_markets)

    # Filter pricing channels available for this commodity in this specific market
    market_crop_df = crop_df[crop_df['market'].str.lower() == selected_market.lower()]
    available_price_types = sorted(market_crop_df['price_type'].dropna().unique())
    selected_price_type = st.sidebar.selectbox("💰 Pricing Type", available_price_types)
else:
    st.sidebar.error("Historical data ledger file missing!")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.write("📊 **Source Data:** Central Bank of Sri Lanka (CBSL)")
st.sidebar.caption("Markets tracked: Pettah, Dambulla, Narahenpita, Peliyagoda, Negombo, Marandagahamula.")

# ----------------------------------------------------------------------
# Main Application Dashboard
# ----------------------------------------------------------------------
st.markdown(f"<h1 class='main-title'>🌾 Govi Gnana (ගොවි ඥාන) Price Advisor</h1>", unsafe_allow_html=True)
st.write(f"**Market Evaluation Date:** {datetime.now().strftime('%Y-%m-%d')} | **Status:** Connected to Groq Cloud Network Engine")

# Crucial Educational Disclaimer Banner Notice Requirement
st.markdown("""
    <div class='disclaimer-box'>
        ⚠️ <b>Educational Purpose Only:</b> This software tool uses Artificial Intelligence and 
        historical statistical baselines to estimate market trend lines. Actual agricultural market spot prices can vary significantly 
        based on weather, logistics, and real-time arrival volumes. Do not base financial contracts solely on these estimations.
    </div>
""", unsafe_allow_html=True)
st.write("")

# Pull specific filtered history to display the line graph immediately
df_crop = market_crop_df[
    market_crop_df['price_type'].str.lower() == selected_price_type.lower()
].sort_values('date')

unit = df_crop['unit'].iloc[-1] if (not df_crop.empty and 'unit' in df_crop.columns) else "Rs./kg"

if not df_crop.empty:
    fig = px.line(
        df_crop, x='date', y='price',
        title=f"📈 Pricing Trend: {selected_crop} at {selected_market} ({selected_price_type})",
        labels={'price': f'Price ({unit})', 'date': 'Date'},
        line_shape='linear',
        template='plotly_white'  # Fallback baseline transparent layout look
    )
    # Style plot elements dynamically to avoid rendering black text on dark interfaces
    fig.update_traces(line_color='#2e7d32', line_width=3)
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='inherit' if st.get_option("theme.base") == "dark" else '#2c3e50')
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"ℹ️ No historical records found matching {selected_crop} in {selected_market} under channels ({selected_price_type}).")

# ----------------------------------------------------------------------
# Multi-Agent Workflow Execution Engine Triggers
# ----------------------------------------------------------------------
st.markdown("### 🔮 Generate Tomorrow's Forecast")
if st.button("Consult AI Market Advisor", type="primary"):
    with st.spinner("🔄 Running multi-agent validation graph and consulting Groq Cloud LLM..."):
        result = predict_crop_price(
            crop=selected_crop, 
            market=selected_market, 
            price_type=selected_price_type
        )

    if result.get("error"):
        st.error(f"❌ Forecasting Engine aborted: {result['error']}")
    else:
        # Display numerical metrics
        col1, col2, col3 = st.columns(3)
        
        current = float(result['current_price'])
        prediction = float(result['prediction'])
        variance = prediction - current
        
        col1.metric(label="Latest Recorded Price", value=f"Rs. {current:.2f}", help=f"Unit: {unit}")
        col2.metric(
            label="Predicted Price (Tomorrow)", 
            value=f"Rs. {prediction:.2f}",
            delta=f"{variance:+.2f} ({unit})",
            help=f"Unit: {unit}"
        )
        col3.metric(label="Calculated 7-Day Running Average", value=f"Rs. {float(result['week_avg']):.2f}", help=f"Unit: {unit}")

        # Market Insights Text Box Configuration
        st.write("")
        st.markdown(f"#### 💡 Market Insight: {result.get('trend', 'stable').upper()} Trend Line Indicator")
        st.markdown(f"""
            <div class='farmer-box'>
                <b>Advisor Evaluation Statement:</b><br/>
                <i>"{result['recommendation']}"</i>
            </div>
        """, unsafe_allow_html=True)

        # Print underlying data sample overview tracking table grid
        st.write("")
        st.subheader("📋 Recent Reference Pricing Rows")
        recent_rows = result['historical_data'][['date', 'market', 'price_type', 'price']].tail(7)
        st.dataframe(
            recent_rows.style.format({'price': 'Rs. {:.2f}'}),
            use_container_width=True,
            hide_index=True
        )

# ----------------------------------------------------------------------
# Footer
# ----------------------------------------------------------------------
st.markdown("---")
st.markdown("""
    <div style='text-align: center; opacity: 0.8; font-size: 0.9em; padding: 10px; line-height: 1.6;'>
        🌱 <b>Govi Gnana</b> is a personal project developed with care for the agricultural community.<br/>
        Designed & Built by <b>Lahiru Januka</b><br/>
        <span style='font-style: italic;'>Computer Science & Engineering Undergraduate | University of Moratuwa (UoM)</span>
    </div>
""", unsafe_allow_html=True)
