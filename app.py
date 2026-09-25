import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="CSV Sector RS Dashboard", layout="wide")

st.title("📊 CSV-Powered Sector RS Dashboard")
st.write("Compare Relative Strength (ROC) rankings dynamically using the sectors and market caps defined in your CSV file.")

# ==========================================
# 1. INGEST DATA FROM UPLOADED CSV
# ==========================================
@st.cache_data
def load_csv_data():
    try:
        # Load the exact file provided verbatim
        df = pd.read_csv("BVVBBVBV (7).csv")
        
        # Clean the text columns to ensure smooth filtering
        df['sector'] = df['sector'].astype(str).str.strip().str.title()
        df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()
        df['marketcapname'] = df['marketcapname'].astype(str).str.strip().str.title()
        
        return df
    except FileNotFoundError:
        return pd.DataFrame()

master_df = load_csv_data()

if master_df.empty:
    st.error('🚨 Could not find the file named "BVVBBVBV (7).csv". Please ensure it is saved in the exact same folder as this Python script.')
    st.stop()

# ==========================================
# 2. SIDEBAR FILTERS (Populated by CSV)
# ==========================================
st.sidebar.header("Dashboard Configuration")

# Dynamically pull unique sectors from the CSV
available_sectors = sorted(master_df['sector'].unique())
selected_sector = st.sidebar.selectbox("Select Sector to Analyze", available_sectors)

# Dynamically pull unique Market Caps from the CSV
available_mcaps = ["All"] + sorted(master_df['marketcapname'].unique().tolist())
selected_mcap = st.sidebar.selectbox("Filter by Market Cap", available_mcaps)

lookback = st.sidebar.number_input("ROC Lookback (Days)", min_value=10, max_value=500, value=250)

# Apply filters to get the target basket of symbols
filtered_df = master_df[master_df['sector'] == selected_sector]
if selected_mcap != "All":
    filtered_df = filtered_df[filtered_df['marketcapname'] == selected_mcap]

active_symbols = filtered_df['Symbol'].tolist()

if not active_symbols:
    st.warning(f"No stocks found for '{selected_sector}' in the '{selected_mcap}' category.")
    st.stop()

# ==========================================
# 3. DATA FETCHING ENGINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_sector_data(symbols, lookback_days):
    yf_symbols = [f"{sym}.NS" for sym in symbols]
    
    # Fetch enough historical data to cover the trading day lookback
    hist = yf.download(yf_symbols, period="2y", interval="1d", progress=False)
    
    if "Close" in hist:
        closes = hist["Close"]
    else:
        closes = hist
        
    closes = closes.ffill().bfill()
    
    data = []
    
    for sym, yf_sym in zip(symbols, yf_symbols):
        if yf_sym in closes.columns:
            series = closes[yf_sym].dropna()
            
            if len(series) >= lookback_days + 1:
                current_price = series.iloc[-1]
                past_price = series.iloc[-(lookback_days + 1)]
                
                # ROC Calculation
                roc = ((current_price - past_price) / past_price) * 100
                data.append({
                    "Symbol": sym, 
                    "Current Price (₹)": current_price,
                    "ROC (%)": roc
                })
            else:
                data.append({
                    "Symbol": sym, 
                    "Current Price (₹)": np.nan,
                    "ROC (%)": np.nan
                })
                
    return pd.DataFrame(data).dropna()

# ==========================================
# 4. DASHBOARD RENDERING
# ==========================================
with st.spinner(f"Fetching market data and calculating {lookback}-day ROC for {len(active_symbols)} stocks..."):
    df = fetch_sector_data(active_symbols, lookback)

if not df.empty:
    st.subheader(f"{selected_sector} Rankings ({selected_mcap})")
    
    # Normalization Processing (Min-Max Scaling to 0-100)
    min_rs = df["ROC (%)"].min()
    max_rs = df["ROC (%)"].max()
    
    if max_rs != min_rs:
        df["Score"] = ((df["ROC (%)"] - min_rs) / (max_rs - min_rs)) * 100
    else:
        df["Score"] = 50.0

    # Merge back with original CSV to pull in the full Company Name
    df = df.merge(master_df[['Symbol', 'Stock Name']], on='Symbol', how='left')

    # Sorting (Descending by Score)
    df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1  # 1-based ranking
    df.index.name = "Rank"
    
    # Formatting
    df["Score"] = df["Score"].round(2)
    df["ROC (%)"] = df["ROC (%)"].round(2)
    df["Current Price (₹)"] = df["Current Price (₹)"].round(2)
    
    # Reorder columns for display
    display_df = df[["Symbol", "Stock Name", "Current Price (₹)", "ROC (%)", "Score"]]
    
    # Color Logic via Pandas Styling
    def apply_color_ranking(data):
        active_count = len(data)
        styles = pd.DataFrame('', index=data.index, columns=data.columns)
        
        for i in range(active_count):
            rank = i + 1
            pct = rank / active_count
            
            # pct <= 0.35 -> Green | pct >= 0.65 -> Red | else -> Gray
            if pct <= 0.35:
                color = "background-color: rgba(0, 128, 0, 0.4); color: white;"
            elif pct >= 0.65:
                color = "background-color: rgba(255, 0, 0, 0.4); color: white;"
            else:
                color = "background-color: rgba(128, 128, 128, 0.4); color: white;"
                
            styles.iloc[i] = color
            
        return styles

    styled_df = display_df.style.apply(apply_color_ranking, axis=None)

    # Render Table
    st.dataframe(styled_df, use_container_width=True, height=800)
    
    # CSV Download
    csv = display_df.to_csv(index=True).encode("utf-8")
    st.download_button(
        label=f"Download {selected_sector} Rankings as CSV", 
        data=csv, 
        file_name=f"{selected_sector.replace(' ', '_')}_rankings.csv", 
        mime="text/csv"
    )
else:
    st.warning("Failed to retrieve market data. Try selecting a different sector.")
