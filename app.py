import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Dynamic RS Dashboard", layout="wide")

st.title("📊 Dynamic CSV Sector RS Dashboard")
st.write("Compare Relative Strength (ROC) rankings dynamically using your custom CSV file.")

# ==========================================
# 1. SIDEBAR FILE UPLOADER
# ==========================================
st.sidebar.header("1. Upload Data")
uploaded_file = st.sidebar.file_uploader("Upload your sector CSV file", type=["csv"])

if not uploaded_file:
    st.info("👆 Please drag and drop your CSV file (e.g., 'BVVBBVBV (7)_2.csv') into the sidebar to get started.")
    st.stop()

# ==========================================
# 2. INGEST DATA FROM UPLOADED CSV
# ==========================================
@st.cache_data
def load_csv_data(file):
    try:
        df = pd.read_csv(file)
        # Clean the text columns to ensure smooth filtering
        # Modify column names below if your CSV headers are spelled differently
        if 'sector' in df.columns:
            df['sector'] = df['sector'].astype(str).str.strip().str.title()
        if 'Symbol' in df.columns:
            df['Symbol'] = df['Symbol'].astype(str).str.strip().str.upper()
        if 'marketcapname' in df.columns:
            df['marketcapname'] = df['marketcapname'].astype(str).str.strip().str.title()
        return df
    except Exception as e:
        st.error(f"Error reading file: {e}")
        return pd.DataFrame()

master_df = load_csv_data(uploaded_file)

if master_df.empty or 'Symbol' not in master_df.columns:
    st.error('🚨 Could not read the data. Please ensure it is a valid CSV file with a "Symbol" column.')
    st.stop()

# ==========================================
# 3. SIDEBAR FILTERS 
# ==========================================
st.sidebar.header("2. Dashboard Configuration")

# Sector Filter (if sector column exists)
if 'sector' in master_df.columns:
    available_sectors = sorted(master_df['sector'].unique())
    selected_sector = st.sidebar.selectbox("Select Sector to Analyze", available_sectors)
    filtered_df = master_df[master_df['sector'] == selected_sector]
else:
    selected_sector = "All Data"
    filtered_df = master_df

# Market Cap Filter (if marketcapname column exists)
if 'marketcapname' in master_df.columns:
    available_mcaps = ["All"] + sorted(master_df['marketcapname'].unique().tolist())
    selected_mcap = st.sidebar.selectbox("Filter by Market Cap", available_mcaps)
    if selected_mcap != "All":
        filtered_df = filtered_df[filtered_df['marketcapname'] == selected_mcap]
else:
    selected_mcap = "All"

lookback = st.sidebar.number_input("ROC Lookback (Days)", min_value=10, max_value=500, value=250)

active_symbols = filtered_df['Symbol'].tolist()

if not active_symbols:
    st.warning("No stocks found for the selected filters.")
    st.stop()

# ==========================================
# 4. DATA FETCHING ENGINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_market_data(symbols, lookback_days):
    yf_symbols = [f"{sym}.NS" for sym in symbols]
    
    # Fetch historical data
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
                
                roc = ((current_price - past_price) / past_price) * 100
                data.append({"Symbol": sym, "Current Price (₹)": current_price, "ROC (%)": roc})
            else:
                data.append({"Symbol": sym, "Current Price (₹)": np.nan, "ROC (%)": np.nan})
                
    return pd.DataFrame(data).dropna()

# ==========================================
# 5. DASHBOARD RENDERING
# ==========================================
with st.spinner(f"Fetching market data and calculating {lookback}-day ROC for {len(active_symbols)} stocks..."):
    df = fetch_market_data(active_symbols, lookback)

if not df.empty:
    st.subheader(f"{selected_sector} Rankings ({selected_mcap})")
    
    # Min-Max Normalization to 0-100 Score
    min_rs = df["ROC (%)"].min()
    max_rs = df["ROC (%)"].max()
    
    if max_rs != min_rs:
        df["Score"] = ((df["ROC (%)"] - min_rs) / (max_rs - min_rs)) * 100
    else:
        df["Score"] = 50.0

    # Merge back original stock names if the column exists
    if 'Stock Name' in master_df.columns:
        df = df.merge(master_df[['Symbol', 'Stock Name']], on='Symbol', how='left')
        display_cols = ["Symbol", "Stock Name", "Current Price (₹)", "ROC (%)", "Score"]
    else:
        display_cols = ["Symbol", "Current Price (₹)", "ROC (%)", "Score"]

    # Sort & Rank
    df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)
    df.index = df.index + 1  
    df.index.name = "Rank"
    
    # Format numbers
    df["Score"] = df["Score"].round(2)
    df["ROC (%)"] = df["ROC (%)"].round(2)
    df["Current Price (₹)"] = df["Current Price (₹)"].round(2)
    
    display_df = df[[col for col in display_cols if col in df.columns]]
    
    # Color Heatmap Logic
    def apply_color_ranking(data):
        active_count = len(data)
        styles = pd.DataFrame('', index=data.index, columns=data.columns)
        
        for i in range(active_count):
            rank = i + 1
            pct = rank / active_count
            
            # Top 35% Green, Bottom 35% Red, Middle Gray
            if pct <= 0.35:
                color = "background-color: rgba(0, 128, 0, 0.4); color: white;"
            elif pct >= 0.65:
                color = "background-color: rgba(255, 0, 0, 0.4); color: white;"
            else:
                color = "background-color: rgba(128, 128, 128, 0.4); color: white;"
                
            styles.iloc[i] = color
        return styles

    styled_df = display_df.style.apply(apply_color_ranking, axis=None)

    # Output to screen
    st.dataframe(styled_df, use_container_width=True, height=800)
    
    # Download Button
    csv = display_df.to_csv(index=True).encode("utf-8")
    st.download_button("Download Rankings as CSV", data=csv, file_name="sector_rankings.csv", mime="text/csv")
else:
    st.warning("Failed to retrieve market data from Yahoo Finance.")
