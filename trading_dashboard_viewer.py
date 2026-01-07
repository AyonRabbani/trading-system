#!/usr/bin/env python3
"""
Trading System Dashboard - VIEW ONLY (Enhanced)

Read-only portfolio monitoring with real-time PM activity feed.
Shows scanning, strategy selection, rebalancing, and profit-taking decisions.

Usage:
    streamlit run trading_dashboard_viewer.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import os
import requests
import time
import html
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import glob
import re
import asyncio
import websockets
from threading import Thread
from queue import Queue

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
    ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
    POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
    ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# File paths
SCAN_RESULTS_PATH = 'scan_results.json'
TRADING_LOG_PATTERN = 'trading_automation_*.log'
PROFIT_TAKER_LOG_PATTERN = 'profit_taker_*.log'
SCANNER_LOG_PATTERN = 'daily_scanner_*.log'

# ============================================================================
# LOG PARSING HELPERS
# ============================================================================

def parse_log_events(log_path: str, max_events: int = 50) -> List[dict]:
    """Parse log file and extract key events."""
    if not os.path.exists(log_path):
        return []
    
    events = []
    
    try:
        with open(log_path, 'r') as f:
            lines = f.readlines()
        
        for line in lines[-max_events:]:
            # Parse timestamp and message
            match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})[,\s]+\-\s+(\w+)\s+\-\s+(.*)', line)
            if match:
                timestamp_str, level, message = match.groups()
                
                # Classify event type
                event_type = 'info'
                icon = 'ℹ️'
                
                if 'ERROR' in level or 'error' in message.lower():
                    event_type = 'error'
                    icon = '❌'
                elif 'WARNING' in level or 'warning' in message.lower():
                    event_type = 'warning'
                    icon = '⚠️'
                elif 'scan' in message.lower() or 'scanner' in message.lower():
                    event_type = 'scan'
                    icon = '🔍'
                elif 'strategy' in message.lower():
                    event_type = 'strategy'
                    icon = '🎯'
                elif 'order' in message.lower() or 'buy' in message.lower() or 'sell' in message.lower():
                    event_type = 'order'
                    icon = '📊'
                elif 'profit' in message.lower() or 'trailing' in message.lower():
                    event_type = 'profit'
                    icon = '💰'
                elif 'rebalance' in message.lower():
                    event_type = 'rebalance'
                    icon = '⚖️'
                
                events.append({
                    'timestamp': timestamp_str,
                    'level': level,
                    'type': event_type,
                    'icon': icon,
                    'message': message.strip()
                })
    
    except Exception as e:
        st.error(f"Error parsing log: {e}")
    
    return events

def get_latest_log_file(pattern: str) -> Optional[str]:
    """Get the most recent log file matching pattern."""
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def aggregate_all_events(max_events: int = 100) -> List[dict]:
    """
    Aggregate events from all sources:
    1. Public events JSON (for cloud/GitHub sync)
    2. Local log files (when running locally)
    """
    all_events = []
    
    # PRIORITY 1: Load from public_events.json (works on cloud + local)
    try:
        if os.path.exists('public_events.json'):
            with open('public_events.json', 'r') as f:
                data = json.load(f)
                public_events = data.get('events', [])
                # Normalize format
                for e in public_events:
                    if 'event_type' not in e and 'type' in e:
                        e['event_type'] = e['type']
                all_events.extend(public_events)
    except Exception as e:
        st.warning(f"Could not load public events: {e}")
    
    # PRIORITY 2: Load from log files (only works locally)
    if not all_events:  # Only parse logs if no public events
        # Get latest log files
        trading_log = get_latest_log_file(TRADING_LOG_PATTERN)
        profit_log = get_latest_log_file(PROFIT_TAKER_LOG_PATTERN)
        scanner_log = get_latest_log_file(SCANNER_LOG_PATTERN)
        
        # Parse each log
        if trading_log:
            events = parse_log_events(trading_log, max_events)
            for e in events:
                e['source'] = 'Trading Automation'
            all_events.extend(events)
        
        if profit_log:
            events = parse_log_events(profit_log, max_events)
            for e in events:
                e['source'] = 'Profit Taker'
            all_events.extend(events)
        
        if scanner_log:
            events = parse_log_events(scanner_log, max_events)
            for e in events:
                e['source'] = 'Market Scanner'
            all_events.extend(events)
    
    # Sort by timestamp descending
    all_events.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return all_events[:max_events]

def extract_strategy_decisions() -> List[dict]:
    """Extract strategy selection decisions from logs."""
    trading_log = get_latest_log_file(TRADING_LOG_PATTERN)
    if not trading_log:
        return []
    
    decisions = []
    
    try:
        with open(trading_log, 'r') as f:
            content = f.read()
        
        # Look for strategy selection patterns
        pattern = r'Selected strategy: (\w+).*NAV: \$?([\d,\.]+)'
        matches = re.findall(pattern, content)
        
        for strategy, nav in matches:
            decisions.append({
                'strategy': strategy,
                'nav': nav,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
    
    except Exception as e:
        pass
    
    return decisions

# ============================================================================
# ALPACA API HELPERS
# ============================================================================

def get_alpaca_headers():
    """Get Alpaca API headers."""
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }

@st.cache_data(ttl=30)
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

@st.cache_data(ttl=15)
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

@st.cache_data(ttl=60)
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

def create_allocation_pie_chart(positions: List[dict]):
    """Create portfolio allocation pie chart."""
    if not positions:
        return None
    
    labels = [p['symbol'] for p in positions]
    values = [float(p['market_value']) for p in positions]
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.3,
        marker=dict(colors=['#00D9FF', '#FF4444', '#00FF00', '#FFD700', '#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A'])
    )])
    
    fig.update_layout(
        title='Portfolio Allocation',
        template='plotly_dark',
        height=400
    )
    
    return fig

def create_activity_timeline(events: List[dict]):
    """Create activity timeline visualization."""
    if not events:
        return None
    
    # Group by type
    event_types = {}
    for event in events:
        event_type = event['type']
        if event_type not in event_types:
            event_types[event_type] = []
        event_types[event_type].append(event)
    
    # Create timeline chart
    fig = go.Figure()
    
    colors = {
        'scan': '#00D9FF',
        'strategy': '#FFD700',
        'order': '#00FF00',
        'profit': '#FF6B6B',
        'rebalance': '#FFA07A',
        'info': '#4ECDC4',
        'warning': '#FF8C00',
        'error': '#FF4444'
    }
    
    for event_type, type_events in event_types.items():
        timestamps = [datetime.strptime(e['timestamp'], '%Y-%m-%d %H:%M:%S') for e in type_events]
        y_values = [event_type] * len(timestamps)
        
        fig.add_trace(go.Scatter(
            x=timestamps,
            y=y_values,
            mode='markers',
            name=event_type.title(),
            marker=dict(
                size=12,
                color=colors.get(event_type, '#FFFFFF'),
                symbol='circle'
            ),
            text=[e['message'][:50] + '...' if len(e['message']) > 50 else e['message'] for e in type_events],
            hovertemplate='%{text}<br>%{x}<extra></extra>'
        ))
    
    fig.update_layout(
        title='Portfolio Manager Activity Timeline',
        xaxis_title='Time',
        yaxis_title='Event Type',
        template='plotly_dark',
        height=300,
        showlegend=True,
        hovermode='closest'
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
        page_title="Portfolio Manager Live Feed",
        page_icon="🤖",
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
        .event-card {
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            border-left: 4px solid #00D9FF;
            background-color: #1E1E1E;
        }
        .event-timestamp {
            color: #888;
            font-size: 12px;
        }
        .event-source {
            color: #00D9FF;
            font-weight: bold;
        }
        .pm-thinking {
            background: linear-gradient(135deg, #1E1E1E 0%, #2D2D2D 100%);
            padding: 15px;
            border-radius: 10px;
            border: 2px solid #00D9FF;
            margin: 10px 0;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.title("🤖 Portfolio Manager Live Feed")
    st.markdown("*Real-time view of every scan, strategy decision, and trade execution*")
    
    # Sidebar
    with st.sidebar:
        st.header("🎛️ Dashboard Controls")
        
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=True)
        show_all_events = st.checkbox("Show all event types", value=True)
        
        if not show_all_events:
            event_filter = st.multiselect(
                "Filter events",
                options=['scan', 'strategy', 'order', 'profit', 'rebalance', 'info', 'warning', 'error'],
                default=['scan', 'strategy', 'order', 'profit']
            )
        else:
            event_filter = None
        
        st.markdown("---")
        
        # System status
        st.subheader("📡 System Status")
        
        # Check for recent log files
        trading_log = get_latest_log_file(TRADING_LOG_PATTERN)
        profit_log = get_latest_log_file(PROFIT_TAKER_LOG_PATTERN)
        scanner_log = get_latest_log_file(SCANNER_LOG_PATTERN)
        
        st.metric("Scanner", "🟢 Active" if scanner_log else "⚪ Inactive")
        st.metric("Trading Bot", "🟢 Active" if trading_log else "⚪ Inactive")
        st.metric("Profit Taker", "🟢 Active" if profit_log else "⚪ Inactive")
        
        st.markdown("---")
        
        if st.button("🔄 Refresh Now"):
            st.cache_data.clear()
            st.rerun()
        
        st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🎯 PM Activity Feed",
        "📊 Portfolio Overview",
        "💼 Positions",
        "🔍 Market Analysis",
        "📜 Recent Orders"
    ])
    
    # ========================================================================
    # TAB 1: PM ACTIVITY FEED (NEW!)
    # ========================================================================
    with tab1:
        st.header("Portfolio Manager Activity Feed")
        st.markdown("*Live stream of scanning, strategy selection, and execution decisions*")
        
        # Get all events
        all_events = aggregate_all_events(max_events=100)
        
        if event_filter:
            all_events = [e for e in all_events if e['type'] in event_filter]
        
        if all_events:
            # Activity timeline
            fig = create_activity_timeline(all_events[:50])
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # Event feed
            st.subheader(f"📋 Recent Events ({len(all_events)})")
            
            for event in all_events[:30]:
                with st.container():
                    col1, col2 = st.columns([1, 20])
                    
                    with col1:
                        # Display icon safely
                        st.markdown(f"<div style='font-size: 24px;'>{event.get('icon', '📊')}</div>", unsafe_allow_html=True)
                    
                    with col2:
                        # Use simple text display to avoid regex issues
                        timestamp = str(event.get('timestamp', ''))[:19]  # Trim to datetime only
                        source = str(event.get('source', 'Unknown'))
                        message = str(event.get('message', ''))
                        
                        # Display with simple styling
                        st.markdown(f"""
                        <div class="event-card">
                            <div class="event-timestamp">{timestamp} | <span class="event-source">{source}</span></div>
                        </div>
                        """, unsafe_allow_html=True)
                        st.text(message)  # Plain text avoids regex issues
        else:
            st.info("No recent activity. The PM may be idle or log files are not available on this deployment.")
            st.markdown("""
            **Note:** This Streamlit Cloud deployment shows portfolio data in real-time via Alpaca API, 
            but PM activity logs are only available when running locally.
            
            **To see full PM activity feed locally:**
            1. Clone the repo: `git clone https://github.com/AyonRabbani/trading-system.git`
            2. Run scanner: `python daily_scanner.py --mode scan`
            3. Run trading bot: `python trading_automation.py --mode dry-run`
            4. Run profit taker: `python intraday_profit_taker.py --mode moderate`
            5. View dashboard: `streamlit run trading_dashboard_viewer.py`
            """)
        
        # PM Decision Summary
        st.markdown("---")
        st.subheader("🧠 PM Decision Summary")
        
        decisions = extract_strategy_decisions()
        if decisions:
            latest_decision = decisions[-1]
            
            st.markdown(f"""
            <div class="pm-thinking">
                <h4>💭 Latest Strategy Selection</h4>
                <p><strong>Chosen Strategy:</strong> {latest_decision['strategy']}</p>
                <p><strong>Portfolio NAV:</strong> ${latest_decision['nav']}</p>
                <p><strong>Decision Time:</strong> {latest_decision['timestamp']}</p>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("No strategy decisions recorded yet.")
    
    # ========================================================================
    # TAB 2: PORTFOLIO OVERVIEW
    # ========================================================================
    with tab2:
        st.header("Portfolio Overview")
        
        # Fetch account data
        account = get_account_info()
        positions = get_positions()
        
        if account:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                equity = float(account.get('equity', 0))
                last_equity = float(account.get('last_equity', equity))
                equity_change = equity - last_equity
                equity_change_pct = (equity_change / last_equity * 100) if last_equity > 0 else 0
                st.metric("Portfolio Value", f"${equity:,.2f}", 
                         delta=f"{equity_change_pct:+.2f}%")
            
            with col2:
                cash = float(account.get('cash', 0))
                cash_pct = (cash / equity * 100) if equity > 0 else 0
                st.metric("Cash", f"${cash:,.2f}", 
                         delta=f"{cash_pct:.1f}% of portfolio")
            
            with col3:
                day_pnl = equity - last_equity
                st.metric("Today's P&L", f"${day_pnl:,.2f}",
                         delta=f"{(day_pnl/last_equity*100):+.2f}%" if last_equity > 0 else "N/A")
            
            with col4:
                num_positions = len(positions)
                total_pl = sum([float(p.get('unrealized_pl', 0)) for p in positions])
                st.metric("Open Positions", num_positions,
                         delta=f"${total_pl:,.2f} total P&L")
        
        st.markdown("---")
        
        # Portfolio performance chart
        history = get_portfolio_history()
        if history and 'timestamp' in history:
            fig = create_portfolio_chart(history)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
            
            # Performance metrics
            equity_values = history['equity']
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_return = ((equity_values[-1] - equity_values[0]) / equity_values[0]) * 100
                st.metric("30-Day Return", f"{total_return:+.2f}%")
            
            with col2:
                max_equity = max(equity_values)
                min_equity = min(equity_values)
                max_drawdown = ((min_equity - max_equity) / max_equity) * 100
                st.metric("Max Drawdown (30D)", f"{max_drawdown:.2f}%")
            
            with col3:
                returns = pd.Series(equity_values).pct_change().dropna()
                volatility = returns.std() * np.sqrt(252) * 100
                st.metric("Annualized Volatility", f"{volatility:.2f}%")
            
            with col4:
                avg_daily_return = returns.mean() * 100
                sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
                st.metric("Sharpe Ratio", f"{sharpe:.2f}")
        else:
            st.warning("Portfolio history not available")
    
    # ========================================================================
    # TAB 3: POSITIONS
    # ========================================================================
    with tab3:
        st.header("Current Positions")
        
        positions = get_positions()
        
        if positions:
            # Charts
            col1, col2 = st.columns(2)
            
            with col1:
                fig = create_positions_chart(positions)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                fig = create_allocation_pie_chart(positions)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")
            
            # Detailed positions table
            st.subheader(f"Position Details ({len(positions)} holdings)")
            
            positions_df = pd.DataFrame([{
                'Ticker': p['symbol'],
                'Shares': int(float(p['qty'])),
                'Entry Price': f"${float(p['avg_entry_price']):.2f}",
                'Current Price': f"${float(p['current_price']):.2f}",
                'Market Value': f"${float(p['market_value']):,.2f}",
                'Unrealized P&L': f"${float(p['unrealized_pl']):,.2f}",
                'P&L %': f"{float(p['unrealized_plpc'])*100:+.2f}%",
                'Today P&L': f"${float(p['unrealized_intraday_pl']):,.2f}",
                'Today P&L %': f"{float(p['unrealized_intraday_plpc'])*100:+.2f}%",
                'Allocation %': f"{(float(p['market_value'])/sum([float(pos['market_value']) for pos in positions])*100):.1f}%"
            } for p in positions])
            
            st.dataframe(positions_df, use_container_width=True)
            
            # Summary stats
            st.markdown("---")
            st.subheader("Position Statistics")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_value = sum([float(p['market_value']) for p in positions])
                st.metric("Total Position Value", f"${total_value:,.2f}")
            
            with col2:
                total_pl = sum([float(p['unrealized_pl']) for p in positions])
                total_pl_pct = (total_pl / (total_value - total_pl) * 100) if (total_value - total_pl) > 0 else 0
                st.metric("Total Unrealized P&L", f"${total_pl:,.2f}", delta=f"{total_pl_pct:+.2f}%")
            
            with col3:
                winners = len([p for p in positions if float(p['unrealized_pl']) > 0])
                win_rate = (winners / len(positions) * 100) if positions else 0
                st.metric("Winning Positions", f"{winners}/{len(positions)}", delta=f"{win_rate:.0f}% win rate")
            
            with col4:
                avg_pl_pct = np.mean([float(p['unrealized_plpc']) * 100 for p in positions])
                st.metric("Avg P&L %", f"{avg_pl_pct:+.2f}%")
            
        else:
            st.info("No open positions")
    
    # ========================================================================
    # TAB 4: MARKET ANALYSIS
    # ========================================================================
    with tab4:
        st.header("Market Analysis & Scanner Results")
        
        scan_results = load_scan_results()
        
        if scan_results:
            timestamp = scan_results.get('timestamp', 'Unknown')
            scan_time = datetime.fromisoformat(timestamp) if timestamp != 'Unknown' else None
            
            if scan_time:
                time_ago = datetime.now() - scan_time
                hours_ago = int(time_ago.total_seconds() / 3600)
                st.info(f"📅 Last scan: {scan_time.strftime('%Y-%m-%d %H:%M:%S')} ({hours_ago}h ago)")
            
            # Market regime
            col1, col2, col3 = st.columns(3)
            
            with col1:
                regime = scan_results.get('market_regime', 'NEUTRAL')
                color = {'RISK_ON': '🟢', 'RISK_OFF': '🔴', 'NEUTRAL': '🟡'}.get(regime, '⚪')
                st.metric("Market Regime", f"{color} {regime}")
            
            with col2:
                hot_sectors = scan_results.get('hot_sectors', [])
                hot_text = ', '.join(hot_sectors[:3]) if hot_sectors else 'N/A'
                st.metric("Hot Sectors", hot_text)
            
            with col3:
                num_recs = len(scan_results.get('rotation_recommendations', []))
                st.metric("Rotation Signals", num_recs)
            
            st.markdown("---")
            
            # Top scorers
            st.subheader("Top Market Opportunities")
            
            scores = scan_results.get('top_scorers', [])
            if scores:
                fig = create_scanner_scores_chart(scores)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                
                # Table
                scores_df = pd.DataFrame([{
                    'Rank': i+1,
                    'Ticker': s['ticker'],
                    'Composite Score': f"{s['composite']:.1f}",
                    'Momentum': f"{s['momentum']:.1f}",
                    'Volatility': f"{s['volatility']:.1f}",
                    'Rel. Strength': f"{s['relative_strength']:.1f}",
                    'Breakout': f"{s['breakout']:.1f}",
                    '30D Return': f"{s['return_30d']:+.1f}%",
                    'Price': f"${s['price']:.2f}"
                } for i, s in enumerate(scores[:20])])
                
                st.dataframe(scores_df, use_container_width=True, height=400)
            
            st.markdown("---")
            
            # Portfolio comparison
            comparison = scan_results.get('portfolio_comparison', {})
            if comparison:
                st.subheader("Portfolio Analysis")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**Current Portfolio Metrics**")
                    current = comparison.get('current', {})
                    
                    metrics_df = pd.DataFrame([
                        ['Sharpe Ratio', f"{current.get('sharpe', 0):.3f}"],
                        ['Annual Return', f"{current.get('annual_return', 0):.1f}%"],
                        ['Annual Volatility', f"{current.get('annual_volatility', 0):.1f}%"],
                        ['Max Drawdown', f"{current.get('max_drawdown', 0):.1f}%"],
                        ['Calmar Ratio', f"{current.get('calmar_ratio', 0):.3f}"],
                        ['Win Rate', f"{current.get('win_rate', 0):.1f}%"]
                    ], columns=['Metric', 'Value'])
                    
                    st.dataframe(metrics_df, use_container_width=True, hide_index=True)
                
                with col2:
                    st.markdown("**Recommended Portfolio Potential**")
                    recommended = comparison.get('recommended', {})
                    improvements = comparison.get('improvements', {})
                    
                    metrics_df = pd.DataFrame([
                        ['Sharpe Ratio', f"{recommended.get('sharpe', 0):.3f}", f"{improvements.get('sharpe', 0):+.3f}"],
                        ['Annual Return', f"{recommended.get('annual_return', 0):.1f}%", f"{improvements.get('return', 0):+.1f}%"],
                        ['Annual Volatility', f"{recommended.get('annual_volatility', 0):.1f}%", f"{improvements.get('volatility', 0):+.1f}%"],
                        ['Max Drawdown', f"{recommended.get('max_drawdown', 0):.1f}%", f"{improvements.get('max_drawdown', 0):+.1f}%"],
                        ['Calmar Ratio', f"{recommended.get('calmar_ratio', 0):.3f}", ''],
                        ['Win Rate', f"{recommended.get('win_rate', 0):.1f}%", '']
                    ], columns=['Metric', 'Value', 'Δ'])
                    
                    st.dataframe(metrics_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No market analysis data available")
    
    # ========================================================================
    # TAB 5: RECENT ORDERS
    # ========================================================================
    with tab5:
        st.header("Recent Trading Activity")
        
        orders = get_orders()
        
        if orders:
            # Filter by status
            status_filter = st.multiselect(
                "Filter by Status",
                options=['filled', 'partially_filled', 'pending_new', 'new', 'canceled', 'rejected'],
                default=['filled', 'partially_filled']
            )
            
            filtered_orders = [o for o in orders if o['status'] in status_filter]
            
            st.subheader(f"Orders ({len(filtered_orders)} shown)")
            
            if filtered_orders:
                orders_df = pd.DataFrame([{
                    'Time': datetime.fromisoformat(o['created_at'].replace('Z', '+00:00')).strftime('%m/%d/%y %H:%M'),
                    'Ticker': o['symbol'],
                    'Side': o['side'].upper(),
                    'Quantity': int(float(o['qty'])),
                    'Type': o['type'].upper(),
                    'Status': o['status'].upper(),
                    'Filled': f"{int(float(o.get('filled_qty', 0)))}/{int(float(o['qty']))}",
                    'Avg Fill Price': f"${float(o.get('filled_avg_price', 0)):.2f}" if o.get('filled_avg_price') else 'N/A',
                    'Time in Force': o.get('time_in_force', 'N/A').upper()
                } for o in filtered_orders])
                
                st.dataframe(orders_df, use_container_width=True, height=500)
                
                # Summary stats
                st.markdown("---")
                st.subheader("Activity Summary")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    total_orders = len(orders)
                    st.metric("Total Orders (50 recent)", total_orders)
                
                with col2:
                    filled_orders = len([o for o in orders if o['status'] == 'filled'])
                    fill_rate = (filled_orders / total_orders * 100) if total_orders > 0 else 0
                    st.metric("Filled Orders", filled_orders, delta=f"{fill_rate:.0f}% fill rate")
                
                with col3:
                    buy_orders = len([o for o in orders if o['side'] == 'buy'])
                    sell_orders = len([o for o in orders if o['side'] == 'sell'])
                    st.metric("Buy/Sell Ratio", f"{buy_orders}/{sell_orders}")
                
                with col4:
                    from datetime import timezone
                    now = datetime.now(timezone.utc)
                    recent_24h = len([o for o in orders if (now - datetime.fromisoformat(o['created_at'].replace('Z', '+00:00'))).days == 0])
                    st.metric("Orders (24h)", recent_24h)
            else:
                st.info("No orders match the selected filters")
        else:
            st.info("No recent orders")
    
    # Footer
    st.markdown("---")
    st.caption(f"🤖 Portfolio Manager Live Feed | Auto-refresh: {'ON' if auto_refresh else 'OFF'} | Last update: {datetime.now().strftime('%H:%M:%S')}")
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(30)
        st.rerun()

if __name__ == '__main__':
    main()
