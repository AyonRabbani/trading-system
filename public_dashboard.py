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
        daily_pl = account['equity'] - account['last_equity']
        daily_pl_pct = (daily_pl / account['last_equity'] * 100) if account['last_equity'] > 0 else 0
        st.metric("Today's P/L", f"${daily_pl:,.2f}", f"{daily_pl_pct:+.2f}%")
    
    st.caption(f"Last updated: {state.get('timestamp', 'Unknown')[:19]}")
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
        'Symbol': p['symbol'],
        'Qty': f"{p['qty']:.2f}",
        'Entry': f"${p['avg_entry_price']:.2f}",
        'Current': f"${p['current_price']:.2f}",
        'Value': f"${p['market_value']:,.2f}",
        'P&L $': f"${p['unrealized_pl']:,.2f}",
        'P&L %': f"{p['unrealized_plpc'] * 100:+.2f}%",
        'Today $': f"${p['unrealized_intraday_pl']:,.2f}",
        'Today %': f"${p['unrealized_intraday_plpc'] * 100:+.2f}%"
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
        st.metric("Total P&L", f"${total_pl:,.2f}")
    
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
