import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="All NSE RS Dashboard", layout="wide")

st.title("🇮🇳 All NSE RS Dashboard")
st.write("Calculates the Rate of Change (ROC), normalizes it to a 0-100 score, and ranks the entire NSE market (35% Green / 35% Red).")

# ==========================================
# 1. FETCH ALL NSE TICKERS
# ==========================================
@st.cache_data(ttl=86400)
def get_nse_tickers():
    url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        df = pd.read_csv(url, storage_options=headers)
        return df["SYMBOL"].str.strip().tolist()
    except Exception:
        st.warning("Could not download live NSE master list. Using fallback list.")
        return ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "ITC", "SBIN", "BHARTIARTL", "LICI"]

all_nse_symbols = get_nse_tickers()

# ==========================================
# 2. SIDEBAR FILTERS
# ==========================================
st.sidebar.header("Dashboard Configuration")

max_stocks = st.sidebar.slider(
    "Max Stocks to Scan (Increase to scan all)", 
    min_value=10, 
    max_value=len(all_nse_symbols), 
    value=100, 
    step=50
)

selected_symbols = st.sidebar.multiselect(
    "Select Specific Stocks (Overrides slider)", 
    all_nse_symbols, 
    default=[]
)

lookback = st.sidebar.number_input("ROC Lookback (Days)", min_value=10, max_value=500, value=250)

# Determine final list of symbols to process
target_symbols = selected_symbols if selected_symbols else all_nse_symbols[:max_stocks]

# ==========================================
# 3. DATA FETCHING ENGINE
# ==========================================
@st.cache_data(ttl=3600)
def fetch_market_data(symbols, lookback_days):
    yf_symbols = [f"{sym}.NS" for sym in symbols]
    
    # Fetch historical data (2 years ensures enough data for a 250+ day lookback)
    hist = yf.download(yf_symbols, period="2y", interval="1d", progress=False)
    
    if "Close" in hist:
        closes = hist["Close"]
    else:
        closes = hist
        
    # Clean missing data for newly listed or halted stocks
    closes = closes.ffill().bfill()
    
    data = []
    
    for sym, yf_sym in zip(symbols, yf_symbols):
        if yf_sym in closes.columns:
            series = closes[yf_sym].dropna()
            
            # Ensure the stock has been trading long enough for the lookback
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
                pass # Skip stocks that are too new to have a 250-day history
                
    return pd.DataFrame(data)

# ==========================================
# 4. DASHBOARD RENDERING
# ==========================================
if st.button("Run Market Scanner"):
    with st.spinner(f"Downloading history and calculating {lookback}-day ROC for {len(target_symbols)} stocks (This may take a moment)..."):
        df = fetch_market_data(target_symbols, lookback)

    if not df.empty:
        st.subheader(f"Market Rankings ({len(df)} Valid Stocks Analyzed)")
        
        # Normalization Processing (Min-Max Scaling to 0-100)
        min_rs = df["ROC (%)"].min()
        max_rs = df["ROC (%)"].max()
        
        if max_rs != min_rs:
            df["Score"] = ((df["ROC (%)"] - min_rs) / (max_rs - min_rs)) * 100
        else:
            df["Score"] = 50.0

        # Sorting (Descending by Score)
        df = df.sort_values(by="Score", ascending=False).reset_index(drop=True)
        df.index = df.index + 1  # 1-based ranking
        df.index.name = "Rank"
        
        # Formatting for readability
        df["Score"] = df["Score"].round(2)
        df["ROC (%)"] = df["ROC (%)"].round(2)
        df["Current Price (₹)"] = df["Current Price (₹)"].round(2)
        
        # Reorder columns for display
        display_df = df[["Symbol", "Current Price (₹)", "ROC (%)", "Score"]]
        
        # Color Logic via Pandas Styling (Top 35% Green, Bottom 35% Red)
        def apply_color_ranking(data):
            active_count = len(data)
            styles = pd.DataFrame('', index=data.index, columns=data.columns)
            
            for i in range(active_count):
                rank = i + 1
                pct = rank / active_count
                
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
        
        # CSV Export
        csv = display_df.to_csv(index=True).encode("utf-8")
        st.download_button("Download Rankings as CSV", data=csv, file_name="nse_market_rankings.csv", mime="text/csv")
        
    else:
        st.warning("Failed to retrieve sufficient data. Stocks may be too new for the chosen lookback period.")
else:
    st.info("Adjust your sidebar filters and click 'Run Market Scanner' to generate the dashboard.")
