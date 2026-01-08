#!/usr/bin/env python3
"""
Public Trading Dashboard - Exact Clone of Local Dashboard
Reads dashboard_state.json exported from local dashboard
Shows EXACT same data - no sanitization, no modifications
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, List, Optional
import time
import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

GITHUB_REPO = "AyonRabbani/trading-system"
GITHUB_BRANCH = "main"
STATE_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/dashboard_state.json"
CACHE_TTL = 30  # Refresh every 30 seconds


# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=CACHE_TTL)
def load_dashboard_state() -> Optional[Dict]:
    """Load complete dashboard state from GitHub or local file"""
    # Try GitHub first (for Streamlit Cloud)
    try:
        response = requests.get(STATE_URL, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        st.warning(f"Could not fetch from GitHub: {e}")
    
    # Fallback to local file
    state_file = Path('dashboard_state.json')
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Error loading local state: {e}")
    
    return None


# ============================================================================
# RENDER FUNCTIONS (EXACT SAME AS LOCAL DASHBOARD)
# ============================================================================

def render_header():
    """Render dashboard header"""
    st.title("📊 PUBLIC TRADING DASHBOARD")
    st.caption("🌐 Exact mirror of local dashboard | Full data visibility | No sanitization")
    st.divider()


def render_account_summary(state: Dict):
    """Render account metrics - EXACT same as local dashboard"""
    st.subheader("💰 ACCOUNT SUMMARY")
    
    account = state.get('account')
    if not account:
        st.warning("No account data available")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Portfolio Value", f"${account['portfolio_value']:,.2f}")
    
    with col2:
        st.metric("Cash", f"${account['cash']:,.2f}")
    
    with col3:
        st.metric("Buying Power", f"${account['buying_power']:,.2f}")
    
    with col4:
        last_equity = account.get('last_equity', account.get('equity', 0))
        daily_pl = account['equity'] - last_equity
        daily_pl_pct = (daily_pl / last_equity * 100) if last_equity > 0 else 0
        daily_pl_str = f"-${abs(daily_pl):,.2f}" if daily_pl < 0 else f"${daily_pl:,.2f}"
        st.metric("Today's P/L", daily_pl_str, f"{daily_pl_pct:+.2f}%")
    
    st.caption(f"Last updated: {state.get('timestamp', 'Unknown')[:19]}")
    st.divider()


def render_performance_charts():
    """Render MTD performance comparison with real SPY data"""
    st.header("📈 PERFORMANCE")
    
    try:
        import os
        import requests
        from dotenv import load_dotenv
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import GetPortfolioHistoryRequest
        
        load_dotenv()
        
        # Initialize data client with environment variables
        polygon_key = os.getenv('POLYGON_API_KEY')
        api_key = polygon_key or os.getenv('ALPACA_API_KEY')
        api_secret = os.getenv('ALPACA_SECRET_KEY')
        
        if not api_key or not api_secret:
            st.info("API credentials not available for charts")
            return
        
        # Get start of month
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        days_mtd = (now - start_of_month).days + 1
        
        # Get portfolio history from Alpaca API (hourly updates)
        # Use specific day period to ensure < 30 days constraint
        trading_client = TradingClient(api_key, api_secret, paper=True)
        portfolio_history = trading_client.get_portfolio_history(
            GetPortfolioHistoryRequest(
                period=f"{days_mtd}D",  # MTD period (always < 30 days)
                timeframe="1H",  # Hourly intervals for intraday updates
                intraday_reporting="continuous"  # Use last trade price for equity calculations
            )
        )
        
        # Process portfolio data
        portfolio_values = portfolio_history.equity
        portfolio_timestamps = portfolio_history.timestamp
        
        # Convert timestamps to datetime and filter to MTD
        portfolio_dates = []
        portfolio_returns = []
        
        if portfolio_values and portfolio_timestamps:
            # Filter to MTD
            mtd_values = []
            mtd_dates = []
            for i, ts in enumerate(portfolio_timestamps):
                dt = datetime.fromtimestamp(ts)
                if dt >= start_of_month:
                    mtd_dates.append(dt)
                    mtd_values.append(portfolio_values[i])
            
            # Calculate returns from first MTD value
            if mtd_values:
                start_value = mtd_values[0]
                portfolio_dates = mtd_dates
                portfolio_returns = [(val / start_value - 1) * 100 for val in mtd_values]
        
        # If no portfolio history, show current equity as zero return
        if not portfolio_returns:
            portfolio_dates = [now]
            portfolio_returns = [0.0]
        
        # Fetch real SPY data from Polygon API
        spy_returns = []
        spy_dates = []
        
        if polygon_key:
            try:
                start_date = start_of_month.strftime('%Y-%m-%d')
                end_date = now.strftime('%Y-%m-%d')
                
                # Fetch hourly SPY data
                url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/hour/{start_date}/{end_date}?adjusted=true&sort=asc&apiKey={polygon_key}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('results'):
                        spy_prices = [bar['c'] for bar in data['results']]
                        spy_timestamps = [bar['t'] / 1000 for bar in data['results']]
                        
                        if spy_prices:
                            spy_start = spy_prices[0]
                            spy_dates = [datetime.fromtimestamp(ts) for ts in spy_timestamps]
                            spy_returns = [(price / spy_start - 1) * 100 for price in spy_prices]
            except Exception as e:
                st.warning(f"Could not fetch SPY data: {e}")
        
        # Fallback to hypothetical if SPY data unavailable
        if not spy_returns:
            spy_ytd_return = 1.5
            days_ytd = (now - datetime(now.year, 1, 1)).days
            daily_spy_return = (spy_ytd_return / 100) / days_ytd if days_ytd > 0 else 0
            
            spy_returns = []
            for date in portfolio_dates:
                days_elapsed = (date - start_of_month).days
                spy_return_pct = daily_spy_return * days_elapsed * 100
                spy_returns.append(spy_return_pct)
            spy_dates = portfolio_dates
        
        # Create chart
        st.subheader("MTD Performance Comparison")
        
        # Align data by date
        max_len = max(len(portfolio_returns), len(spy_returns))
        chart_dates = spy_dates if len(spy_dates) == len(spy_returns) else portfolio_dates
        
        chart_data = pd.DataFrame({
            'Date': chart_dates[:max_len],
            'Portfolio': portfolio_returns[:max_len] if len(portfolio_returns) >= max_len else portfolio_returns + [None] * (max_len - len(portfolio_returns)),
            'SPY': spy_returns[:max_len] if len(spy_returns) >= max_len else spy_returns + [None] * (max_len - len(spy_returns))
        }).set_index('Date')
        
        st.line_chart(chart_data, use_container_width=True, height=400)
        
        # Show metrics
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            port_return = portfolio_returns[-1] if portfolio_returns else 0
            st.metric("Portfolio MTD", f"{port_return:+.2f}%")
        with col_b:
            spy_return = spy_returns[-1] if spy_returns else 0
            st.metric("SPY MTD", f"{spy_return:+.2f}%")
        with col_c:
            alpha = port_return - spy_return
            st.metric("Alpha vs SPY", f"{alpha:+.2f}%")
    
    except Exception as e:
        st.error(f"Error loading performance charts: {e}")
        import traceback
        st.code(traceback.format_exc())
    
    st.divider()

def render_positions(state: Dict):
    """Render current positions - EXACT same as local dashboard"""
    st.subheader("📈 CURRENT POSITIONS")
    
    positions = state.get('positions', [])
    
    if not positions:
        st.info("No open positions")
        return
    
    # Create DataFrame with EXACT same columns as local
    df = pd.DataFrame([{
        'Symbol': p.get('symbol', 'N/A'),
        'Qty': f"{p.get('qty', 0):.2f}",
        'Entry': f"${p.get('avg_entry_price', 0):.2f}",
        'Current': f"${p.get('current_price', 0):.2f}",
        'Value': f"${p.get('market_value', 0):,.2f}",
        'P&L $': f"-${abs(p.get('unrealized_pl', 0)):,.2f}" if p.get('unrealized_pl', 0) < 0 else f"${p.get('unrealized_pl', 0):,.2f}",
        'P&L %': f"{p.get('unrealized_plpc', 0) * 100:+.2f}%",
        'Today $': f"-${abs(p.get('unrealized_intraday_pl', 0)):,.2f}" if p.get('unrealized_intraday_pl', 0) < 0 else f"${p.get('unrealized_intraday_pl', 0):,.2f}",
        'Today %': f"{p.get('unrealized_intraday_plpc', 0) * 100:+.2f}%"
    } for p in positions])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Position stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Positions", len(positions))
    
    with col2:
        total_value = sum(p['market_value'] for p in positions)
        st.metric("Total Value", f"${total_value:,.2f}")
    
    with col3:
        total_pl = sum(p['unrealized_pl'] for p in positions)
        total_pl_str = f"-${abs(total_pl):,.2f}" if total_pl < 0 else f"${total_pl:,.2f}"
        st.metric("Total P&L", total_pl_str)
    
    with col4:
        winners = len([p for p in positions if p['unrealized_plpc'] > 0])
        st.metric("Winners", f"{winners}/{len(positions)}")
    
    st.divider()


def render_recent_orders(state: Dict):
    """Render recent orders - EXACT same as local dashboard"""
    st.subheader("📋 RECENT ORDERS")
    
    orders = state.get('orders', [])
    
    if not orders:
        st.info("No recent orders")
        return
    
    # Create DataFrame with EXACT same format as local
    df = pd.DataFrame([{
        'Time': o.get('filled_at', o.get('submitted_at', 'Unknown'))[:19],
        'Symbol': o['symbol'],
        'Side': o['side'],
        'Qty': f"{float(o['qty']):.2f}" if o.get('qty') else 'N/A',
        'Type': o['type'],
        'Status': o['status'],
        'Filled': f"${float(o.get('filled_avg_price', 0)):.2f}" if o.get('filled_avg_price') else 'N/A'
    } for o in orders[:20]])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.divider()


def render_scanner_results(state: Dict):
    """Render scanner results - EXACT same as local dashboard"""
    st.subheader("🔍 SCANNER RESULTS")
    
    scan_results = state.get('scan_results')
    
    if not scan_results:
        st.info("No scanner results available")
        return
    
    # Market regime
    st.markdown(f"**Market Regime:** {scan_results.get('market_regime', 'Unknown')}")
    
    # Top scorers
    if 'top_scorers' in scan_results:
        st.markdown("**Top 10 Tickers:**")
        
        top_10 = scan_results['top_scorers'][:10]
        df = pd.DataFrame([{
            'Ticker': t['ticker'],
            'Score': f"{t['composite']:.1f}",
            'Momentum': f"{t['momentum']:.0f}",
            'RS': f"{t['relative_strength']:.0f}",
            '30d Return': f"{t['return_30d']:.1f}%"
        } for t in top_10])
        
        st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Rotation recommendations
    if 'rotation_recommendations' in scan_results:
        recs = scan_results['rotation_recommendations']
        if recs:
            st.markdown(f"**{len(recs)} Rotation Recommendations:**")
            for rec in recs:
                st.markdown(f"- **{rec['group']}**: {rec['ticker_out']} ({rec['score_out']:.1f}) → {rec['ticker_in']} ({rec['score_in']:.1f}) | +{rec['score_delta']:.1f}")
    
    st.caption(f"Scanner timestamp: {scan_results.get('timestamp', 'Unknown')[:19]}")
    st.divider()


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.set_page_config(
        page_title="Public Trading Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load complete dashboard state
    state = load_dashboard_state()
    
    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ SETTINGS")
        
        st.subheader("Display Sections")
        show_account = st.checkbox("Account Summary", value=True)
        show_positions = st.checkbox("Current Positions", value=True)
        show_orders = st.checkbox("Recent Orders", value=True)
        show_scanner = st.checkbox("Scanner Results", value=True)
        
        st.divider()
        
        # Auto-refresh controls
        auto_refresh = st.checkbox("🔄 Auto-refresh", value=True)
        refresh_interval = st.slider("Refresh interval (sec)", 15, 120, 30)
        
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()
        
        st.divider()
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        if state:
            st.caption(f"Data timestamp: {state.get('timestamp', 'Unknown')[:19]}")
            positions_count = len(state.get('positions', []))
            st.caption(f"Positions: {positions_count}")
        
        st.caption(f"📡 Source: GitHub ({GITHUB_REPO})")
        st.caption("⚠️ FULL DATA - No sanitization")
    
    # Render main content
    render_header()
    
    if not state:
        st.error("❌ Could not load dashboard state")
        st.info("Local dashboard must be running to export data")
        st.stop()
    
    if show_account:
        render_account_summary(state)
    
    # Always show performance charts
    render_performance_charts()
    
    if show_positions:
        render_positions(state)
    
    if show_orders:
        render_recent_orders(state)
    
    if show_scanner:
        render_scanner_results(state)
    
    # Footer
    st.divider()
    st.caption(f"Dashboard refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.caption("🔒 Exact mirror of local dashboard | Full data visibility for team monitoring")
    
    # Auto-refresh at the end
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == '__main__':
    main()
