#!/usr/bin/env python3
"""
Trading System Dashboard - Streamlit UI

Unified interface for daily_scanner.py, trading_automation.py, and intraday_profit_taker.py
Provides real-time monitoring, control panels, and analytics visualization.

Usage:
    streamlit run trading_dashboard.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import subprocess
import threading
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ============================================================================
# CONFIGURATION
# ============================================================================

# Try Streamlit secrets first, fallback to environment variables
try:
    ALPACA_API_KEY = st.secrets["ALPACA_API_KEY"]
    ALPACA_SECRET_KEY = st.secrets["ALPACA_SECRET_KEY"]
    POLYGON_API_KEY = st.secrets["POLYGON_API_KEY"]
    ALPACA_BASE_URL = st.secrets.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
except:
    # Fallback to environment variables (for local development)
    from dotenv import load_dotenv
    load_dotenv()
    ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
    ALPACA_SECRET_KEY = os.getenv('ALPACA_API_SECRET')
    ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
    POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# File paths
SCAN_RESULTS_PATH = 'scan_results.json'
TRADING_LOG_PATH = f'trading_automation_{datetime.now().strftime("%Y%m%d")}.log'
PROFIT_TAKER_LOG_PATH = f'profit_taker_{datetime.now().strftime("%Y%m%d")}.log'
SCANNER_LOG_PATH = f'daily_scanner_{datetime.now().strftime("%Y%m%d")}.log'

# Process tracking
if 'processes' not in st.session_state:
    st.session_state.processes = {
        'scanner': None,
        'trading': None,
        'profit_taker': None
    }

if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# ============================================================================
# ALPACA API HELPERS
# ============================================================================

def get_alpaca_headers():
    """Get Alpaca API headers."""
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }

@st.cache_data(ttl=10)
def get_account_info():
    """Fetch Alpaca account information."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/account"
        response = requests.get(url, headers=get_alpaca_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching account info: {e}")
        return {}

@st.cache_data(ttl=5)
def get_positions():
    """Fetch current positions from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/positions"
        response = requests.get(url, headers=get_alpaca_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching positions: {e}")
        return []

@st.cache_data(ttl=60)
def get_orders():
    """Fetch recent orders from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/orders?status=all&limit=50"
        response = requests.get(url, headers=get_alpaca_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching orders: {e}")
        return []

@st.cache_data(ttl=30)
def get_portfolio_history():
    """Fetch portfolio history from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/account/portfolio/history?period=1M&timeframe=1D"
        response = requests.get(url, headers=get_alpaca_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"Error fetching portfolio history: {e}")
        return {}

# ============================================================================
# SCANNER DATA HELPERS
# ============================================================================

def load_scan_results():
    """Load latest scan results from JSON."""
    if not os.path.exists(SCAN_RESULTS_PATH):
        return None
    
    try:
        with open(SCAN_RESULTS_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading scan results: {e}")
        return None

def read_log_file(log_path: str, max_lines: int = 100):
    """Read last N lines from log file."""
    if not os.path.exists(log_path):
        return []
    
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
            return lines[-max_lines:]
    except Exception as e:
        return [f"Error reading log: {e}"]

# ============================================================================
# PROCESS MANAGEMENT
# ============================================================================

def run_scanner(export_path: str = SCAN_RESULTS_PATH):
    """Run daily scanner in background."""
    try:
        cmd = ['python', 'daily_scanner.py', '--mode', 'scan', '--export', export_path]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        st.session_state.processes['scanner'] = process
        return True
    except Exception as e:
        st.error(f"Error starting scanner: {e}")
        return False

def run_trading_automation(mode: str = 'dry-run', use_scanner: bool = True):
    """Run trading automation in background."""
    try:
        cmd = ['python', 'trading_automation.py', '--mode', mode]
        if use_scanner:
            cmd.extend(['--use-scanner'])
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        st.session_state.processes['trading'] = process
        return True
    except Exception as e:
        st.error(f"Error starting trading automation: {e}")
        return False

def run_profit_taker(mode: str = 'moderate', min_profit: float = 2.0):
    """Run intraday profit taker in background."""
    try:
        cmd = ['python', 'intraday_profit_taker.py', '--mode', mode, '--min-profit', str(min_profit)]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        st.session_state.processes['profit_taker'] = process
        return True
    except Exception as e:
        st.error(f"Error starting profit taker: {e}")
        return False

def stop_process(process_name: str):
    """Stop a running process."""
    process = st.session_state.processes.get(process_name)
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        st.session_state.processes[process_name] = None
        return True
    return False

def check_process_status(process_name: str) -> str:
    """Check if process is running."""
    process = st.session_state.processes.get(process_name)
    if process is None:
        return "Stopped"
    elif process.poll() is None:
        return "Running"
    else:
        return "Completed"

# ============================================================================
# VISUALIZATION HELPERS
# ============================================================================

def create_portfolio_chart(history_data: dict):
    """Create portfolio performance chart."""
    if not history_data or 'timestamp' not in history_data:
        return None
    
    timestamps = [datetime.fromtimestamp(ts) for ts in history_data['timestamp']]
    equity = history_data['equity']
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=equity,
        mode='lines',
        name='Portfolio Value',
        line=dict(color='#00D9FF', width=2),
        fill='tozeroy',
        fillcolor='rgba(0, 217, 255, 0.1)'
    ))
    
    fig.update_layout(
        title='Portfolio Performance (30 Days)',
        xaxis_title='Date',
        yaxis_title='Account Value ($)',
        template='plotly_dark',
        height=400,
        hovermode='x unified'
    )
    
    return fig

def create_positions_chart(positions: List[dict]):
    """Create positions breakdown chart."""
    if not positions:
        return None
    
    tickers = [p['symbol'] for p in positions]
    values = [float(p['market_value']) for p in positions]
    pnl = [float(p['unrealized_pl']) for p in positions]
    colors = ['#00D9FF' if x >= 0 else '#FF4444' for x in pnl]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=tickers,
        y=values,
        marker_color=colors,
        text=[f"${v:,.0f}<br>{p:+.1f}%" for v, p in zip(values, [float(pos['unrealized_plpc'])*100 for pos in positions])],
        textposition='outside',
        hovertemplate='%{x}<br>Value: $%{y:,.2f}<extra></extra>'
    ))
    
    fig.update_layout(
        title='Current Positions',
        xaxis_title='Ticker',
        yaxis_title='Market Value ($)',
        template='plotly_dark',
        height=400,
        showlegend=False
    )
    
    return fig

def create_scanner_scores_chart(scores: List[dict]):
    """Create top scorers bar chart."""
    if not scores:
        return None
    
    top_10 = scores[:10]
    tickers = [s['ticker'] for s in top_10]
    composites = [s['composite'] for s in top_10]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=composites,
        y=tickers,
        orientation='h',
        marker_color='#00D9FF',
        text=[f"{c:.1f}" for c in composites],
        textposition='outside'
    ))
    
    fig.update_layout(
        title='Top 10 Tickers by Composite Score',
        xaxis_title='Composite Score',
        yaxis_title='Ticker',
        template='plotly_dark',
        height=400,
        yaxis={'categoryorder': 'total ascending'}
    )
    
    return fig

# ============================================================================
# STREAMLIT UI
# ============================================================================

def main():
    """Main Streamlit app."""
    
    # Page config
    st.set_page_config(
        page_title="Trading System Dashboard",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .stMetric {
            background-color: #1E1E1E;
            padding: 10px;
            border-radius: 5px;
        }
        .status-running { color: #00D9FF; }
        .status-stopped { color: #FF4444; }
        .status-completed { color: #00FF00; }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.title("📈 Trading System Dashboard")
    st.markdown("*Unified control panel for Scanner, Trading Automation & Profit Taker*")
    
    # Sidebar - Process Controls
    st.sidebar.header("🎛️ Process Controls")
    
    # Auto-refresh
    auto_refresh = st.sidebar.checkbox("Auto-refresh (10s)", value=True)
    if auto_refresh:
        time.sleep(10)
        st.rerun()
    
    st.sidebar.markdown("---")
    
    # Scanner Controls
    st.sidebar.subheader("1️⃣ Daily Scanner")
    scanner_status = check_process_status('scanner')
    st.sidebar.markdown(f"Status: <span class='status-{scanner_status.lower()}'>{scanner_status}</span>", unsafe_allow_html=True)
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("▶️ Start Scanner", disabled=(scanner_status == "Running")):
            if run_scanner():
                st.success("Scanner started!")
                st.rerun()
    with col2:
        if st.button("⏹️ Stop Scanner", disabled=(scanner_status != "Running")):
            if stop_process('scanner'):
                st.success("Scanner stopped!")
                st.rerun()
    
    st.sidebar.markdown("---")
    
    # Trading Automation Controls
    st.sidebar.subheader("2️⃣ Trading Automation")
    trading_status = check_process_status('trading')
    st.sidebar.markdown(f"Status: <span class='status-{trading_status.lower()}'>{trading_status}</span>", unsafe_allow_html=True)
    
    trading_mode = st.sidebar.selectbox("Mode", ["dry-run", "live"], key="trading_mode")
    use_scanner = st.sidebar.checkbox("Use Scanner Results", value=True, key="use_scanner")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("▶️ Start Trading", disabled=(trading_status == "Running")):
            if run_trading_automation(mode=trading_mode, use_scanner=use_scanner):
                st.success("Trading automation started!")
                st.rerun()
    with col2:
        if st.button("⏹️ Stop Trading", disabled=(trading_status != "Running")):
            if stop_process('trading'):
                st.success("Trading automation stopped!")
                st.rerun()
    
    st.sidebar.markdown("---")
    
    # Profit Taker Controls
    st.sidebar.subheader("3️⃣ Intraday Profit Taker")
    profit_taker_status = check_process_status('profit_taker')
    st.sidebar.markdown(f"Status: <span class='status-{profit_taker_status.lower()}'>{profit_taker_status}</span>", unsafe_allow_html=True)
    
    profit_mode = st.sidebar.selectbox("Mode", ["aggressive", "moderate", "conservative"], index=1, key="profit_mode")
    min_profit = st.sidebar.slider("Min Profit %", 1.0, 10.0, 2.0, 0.5, key="min_profit")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("▶️ Start Monitor", disabled=(profit_taker_status == "Running")):
            if run_profit_taker(mode=profit_mode, min_profit=min_profit):
                st.success("Profit taker started!")
                st.rerun()
    with col2:
        if st.button("⏹️ Stop Monitor", disabled=(profit_taker_status != "Running")):
            if stop_process('profit_taker'):
                st.success("Profit taker stopped!")
                st.rerun()
    
    st.sidebar.markdown("---")
    
    # Emergency stop
    if st.sidebar.button("🛑 STOP ALL PROCESSES", type="primary"):
        stopped = []
        for name in ['scanner', 'trading', 'profit_taker']:
            if stop_process(name):
                stopped.append(name)
        if stopped:
            st.sidebar.success(f"Stopped: {', '.join(stopped)}")
        st.rerun()
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "🔍 Scanner Results",
        "💼 Positions & Orders",
        "📈 Performance",
        "📋 Logs"
    ])
    
    # ========================================================================
    # TAB 1: OVERVIEW
    # ========================================================================
    with tab1:
        st.header("Account Overview")
        
        # Fetch account data
        account = get_account_info()
        positions = get_positions()
        
        if account:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                equity = float(account.get('equity', 0))
                st.metric("Account Value", f"${equity:,.2f}")
            
            with col2:
                cash = float(account.get('cash', 0))
                st.metric("Cash Available", f"${cash:,.2f}")
            
            with col3:
                buying_power = float(account.get('buying_power', 0))
                st.metric("Buying Power", f"${buying_power:,.2f}")
            
            with col4:
                day_pnl = float(account.get('equity', 0)) - float(account.get('last_equity', 0))
                st.metric("Day P&L", f"${day_pnl:,.2f}", delta=f"{day_pnl/float(account.get('last_equity', 1))*100:.2f}%")
        
        st.markdown("---")
        
        # Positions summary
        if positions:
            st.subheader(f"Current Positions ({len(positions)} holdings)")
            
            positions_df = pd.DataFrame([{
                'Ticker': p['symbol'],
                'Shares': int(float(p['qty'])),
                'Entry': f"${float(p['avg_entry_price']):.2f}",
                'Current': f"${float(p['current_price']):.2f}",
                'Value': f"${float(p['market_value']):,.2f}",
                'P&L': f"${float(p['unrealized_pl']):,.2f}",
                'P&L %': f"{float(p['unrealized_plpc'])*100:+.2f}%"
            } for p in positions])
            
            st.dataframe(positions_df, use_container_width=True)
            
            # Chart
            fig = create_positions_chart(positions)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No open positions")
        
        st.markdown("---")
        
        # System status
        st.subheader("System Status")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown(f"**Scanner:** <span class='status-{scanner_status.lower()}'>{scanner_status}</span>", unsafe_allow_html=True)
        with col2:
            st.markdown(f"**Trading:** <span class='status-{trading_status.lower()}'>{trading_status}</span>", unsafe_allow_html=True)
        with col3:
            st.markdown(f"**Profit Taker:** <span class='status-{profit_taker_status.lower()}'>{profit_taker_status}</span>", unsafe_allow_html=True)
    
    # ========================================================================
    # TAB 2: SCANNER RESULTS
    # ========================================================================
    with tab2:
        st.header("Daily Scanner Results")
        
        scan_results = load_scan_results()
        
        if scan_results:
            timestamp = scan_results.get('timestamp', 'Unknown')
            st.info(f"Last scan: {timestamp}")
            
            # Market regime
            col1, col2, col3 = st.columns(3)
            
            with col1:
                regime = scan_results.get('market_regime', 'NEUTRAL')
                color = {'RISK_ON': '🟢', 'RISK_OFF': '🔴', 'NEUTRAL': '🟡'}.get(regime, '⚪')
                st.metric("Market Regime", f"{color} {regime}")
            
            with col2:
                hot_sectors = ', '.join(scan_results.get('hot_sectors', [])[:3])
                st.metric("Hot Sectors", hot_sectors)
            
            with col3:
                num_recs = len(scan_results.get('rotation_recommendations', []))
                st.metric("Rotation Recommendations", num_recs)
            
            st.markdown("---")
            
            # Top scorers
            st.subheader("Top Scoring Opportunities")
            
            scores = scan_results.get('top_scorers', [])
            if scores:
                fig = create_scanner_scores_chart(scores)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                
                # Table
                scores_df = pd.DataFrame([{
                    'Rank': i+1,
                    'Ticker': s['ticker'],
                    'Score': f"{s['composite']:.1f}",
                    'Momentum': f"{s['momentum']:.1f}",
                    'Volatility': f"{s['volatility']:.1f}",
                    'Rel. Strength': f"{s['relative_strength']:.1f}",
                    'Breakout': f"{s['breakout']:.1f}",
                    'Return 30D': f"{s['return_30d']:+.1f}%"
                } for i, s in enumerate(scores[:20])])
                
                st.dataframe(scores_df, use_container_width=True)
            
            st.markdown("---")
            
            # Rotation recommendations
            st.subheader("Rotation Recommendations")
            
            recommendations = scan_results.get('rotation_recommendations', [])
            if recommendations:
                for rec in recommendations:
                    with st.expander(f"{rec['group']}: {rec['ticker_out']} → {rec['ticker_in']}"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Out", rec['ticker_out'], f"Score: {rec['score_out']}")
                        with col2:
                            st.metric("In", rec['ticker_in'], f"Score: {rec['score_in']}")
                        with col3:
                            st.metric("Improvement", f"+{rec['score_delta']:.1f}", delta_color="normal")
                        st.info(rec['reason'])
            else:
                st.success("✅ No rotations recommended - current holdings optimal")
            
            st.markdown("---")
            
            # Portfolio comparison
            st.subheader("Portfolio Comparison")
            
            comparison = scan_results.get('portfolio_comparison', {})
            if comparison:
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Current Portfolio**")
                    current = comparison.get('current', {})
                    st.metric("Sharpe Ratio", f"{current.get('sharpe', 0):.3f}")
                    st.metric("Annual Return", f"{current.get('annual_return', 0):.1f}%")
                    st.metric("Volatility", f"{current.get('annual_volatility', 0):.1f}%")
                    st.metric("Max Drawdown", f"{current.get('max_drawdown', 0):.1f}%")
                
                with col2:
                    st.markdown("**Recommended Portfolio**")
                    recommended = comparison.get('recommended', {})
                    improvements = comparison.get('improvements', {})
                    st.metric("Sharpe Ratio", f"{recommended.get('sharpe', 0):.3f}", 
                             delta=f"{improvements.get('sharpe', 0):+.3f}")
                    st.metric("Annual Return", f"{recommended.get('annual_return', 0):.1f}%",
                             delta=f"{improvements.get('return', 0):+.1f}%")
                    st.metric("Volatility", f"{recommended.get('annual_volatility', 0):.1f}%",
                             delta=f"{improvements.get('volatility', 0):+.1f}%")
                    st.metric("Max Drawdown", f"{recommended.get('max_drawdown', 0):.1f}%",
                             delta=f"{improvements.get('max_drawdown', 0):+.1f}%")
        else:
            st.warning("No scan results available. Run the scanner to see recommendations.")
            if st.button("Run Scanner Now"):
                if run_scanner():
                    st.success("Scanner started! Refresh to see results.")
    
    # ========================================================================
    # TAB 3: POSITIONS & ORDERS
    # ========================================================================
    with tab3:
        st.header("Positions & Orders")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Current Positions")
            positions = get_positions()
            
            if positions:
                for p in positions:
                    with st.expander(f"{p['symbol']} - {int(float(p['qty']))} shares"):
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.metric("Entry Price", f"${float(p['avg_entry_price']):.2f}")
                            st.metric("Current Price", f"${float(p['current_price']):.2f}")
                            st.metric("Market Value", f"${float(p['market_value']):,.2f}")
                        with col_b:
                            st.metric("Unrealized P&L", 
                                     f"${float(p['unrealized_pl']):,.2f}",
                                     delta=f"{float(p['unrealized_plpc'])*100:.2f}%")
                            st.metric("Today's P&L", 
                                     f"${float(p['unrealized_intraday_pl']):,.2f}",
                                     delta=f"{float(p['unrealized_intraday_plpc'])*100:.2f}%")
            else:
                st.info("No open positions")
        
        with col2:
            st.subheader("Recent Orders (Last 50)")
            orders = get_orders()
            
            if orders:
                orders_df = pd.DataFrame([{
                    'Time': datetime.fromisoformat(o['created_at'].replace('Z', '+00:00')).strftime('%m/%d %H:%M'),
                    'Ticker': o['symbol'],
                    'Side': o['side'].upper(),
                    'Qty': int(float(o['qty'])),
                    'Type': o['type'].upper(),
                    'Status': o['status'].upper(),
                    'Filled': f"{int(float(o.get('filled_qty', 0)))}/{int(float(o['qty']))}"
                } for o in orders[:50]])
                
                st.dataframe(orders_df, use_container_width=True, height=400)
            else:
                st.info("No recent orders")
    
    # ========================================================================
    # TAB 4: PERFORMANCE
    # ========================================================================
    with tab4:
        st.header("Portfolio Performance")
        
        history = get_portfolio_history()
        
        if history and 'timestamp' in history:
            # Chart
            fig = create_portfolio_chart(history)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            
            # Metrics
            equity_values = history['equity']
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_return = ((equity_values[-1] - equity_values[0]) / equity_values[0]) * 100
                st.metric("30-Day Return", f"{total_return:+.2f}%")
            
            with col2:
                max_equity = max(equity_values)
                drawdown = ((equity_values[-1] - max_equity) / max_equity) * 100
                st.metric("Drawdown from Peak", f"{drawdown:.2f}%")
            
            with col3:
                returns = pd.Series(equity_values).pct_change().dropna()
                volatility = returns.std() * np.sqrt(252) * 100
                st.metric("Annualized Volatility", f"{volatility:.2f}%")
            
            with col4:
                sharpe = (total_return / (volatility/np.sqrt(12))) if volatility > 0 else 0
                st.metric("Sharpe Ratio (30D)", f"{sharpe:.2f}")
        else:
            st.warning("No portfolio history available")
    
    # ========================================================================
    # TAB 5: LOGS
    # ========================================================================
    with tab5:
        st.header("System Logs")
        
        log_type = st.selectbox("Select Log", [
            "Scanner",
            "Trading Automation",
            "Profit Taker"
        ])
        
        log_paths = {
            "Scanner": SCANNER_LOG_PATH,
            "Trading Automation": TRADING_LOG_PATH,
            "Profit Taker": PROFIT_TAKER_LOG_PATH
        }
        
        log_path = log_paths[log_type]
        lines = read_log_file(log_path, max_lines=200)
        
        if lines:
            # Display in code block
            log_text = ''.join(lines)
            st.code(log_text, language='log')
        else:
            st.info(f"No log file found: {log_path}")
        
        # Refresh button
        if st.button("🔄 Refresh Logs"):
            st.rerun()
    
    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
               f"Auto-refresh: {'ON' if auto_refresh else 'OFF'}")

if __name__ == '__main__':
    main()
