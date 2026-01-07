#!/usr/bin/env python3
"""
Trading System Dashboard - VIEW ONLY

Read-only portfolio monitoring dashboard for public sharing.
No trading controls - displays portfolio performance, positions, and analytics only.

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
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import plotly.graph_objects as go

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
        page_title="Portfolio Viewer",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Custom CSS
    st.markdown("""
        <style>
        .stMetric {
            background-color: #1E1E1E;
            padding: 10px;
            border-radius: 5px;
        }
        .big-font {
            font-size: 20px !important;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.title("📊 Portfolio Viewer")
    st.markdown("*Real-time portfolio monitoring and analytics*")
    
    # Sidebar - Info only
    with st.sidebar:
        st.header("ℹ️ About")
        st.info("""
        **View-Only Dashboard**
        
        This is a read-only view of the trading portfolio. 
        All trading operations are managed externally.
        
        Data refreshes automatically every 30 seconds.
        """)
        
        st.markdown("---")
        
        # Manual refresh button
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()
        
        st.markdown("---")
        
        # Display last update time
        st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Portfolio Overview",
        "💼 Positions & Performance",
        "🔍 Market Analysis",
        "📜 Recent Activity"
    ])
    
    # ========================================================================
    # TAB 1: PORTFOLIO OVERVIEW
    # ========================================================================
    with tab1:
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
    # TAB 2: POSITIONS & PERFORMANCE
    # ========================================================================
    with tab2:
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
    # TAB 3: MARKET ANALYSIS
    # ========================================================================
    with tab3:
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
    # TAB 4: RECENT ACTIVITY
    # ========================================================================
    with tab4:
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
    st.caption(f"🔒 View-Only Dashboard | Data updates every 30 seconds | Last refresh: {datetime.now().strftime('%H:%M:%S')}")
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(30)
        st.rerun()

if __name__ == '__main__':
    main()
