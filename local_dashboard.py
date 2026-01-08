#!/usr/bin/env python3
"""
Local Trading Dashboard
Terminal-style viewer with live API data from Alpaca
Displays: Portfolio Manager logs, Profit Taker status, Scanner results, NAV/Positions
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import time
import requests

# Alpaca imports
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest, GetPortfolioHistoryRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Initialize Alpaca clients
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

trading_client = None
if ALPACA_API_KEY and ALPACA_SECRET_KEY:
    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)


# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_scan_results() -> Optional[Dict]:
    """Load latest scanner results"""
    scan_file = Path('scan_results.json')
    if scan_file.exists():
        try:
            with open(scan_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            st.error(f"Error loading scan results: {e}")
    return None


def load_log_file(pattern: str, max_lines: int = 100) -> List[str]:
    """Load recent lines from log file"""
    logs_dir = Path('.')
    log_files = sorted(logs_dir.glob(pattern), key=lambda x: x.stat().st_mtime, reverse=True)
    
    if log_files:
        try:
            with open(log_files[0], 'r') as f:
                lines = f.readlines()
                return lines[-max_lines:]
        except Exception as e:
            return [f"Error reading log: {e}"]
    return []


def get_account_info() -> Optional[Dict]:
    """Get account information from Alpaca"""
    if not trading_client:
        return None
    try:
        account = trading_client.get_account()
        return {
            'equity': float(account.equity),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power),
            'portfolio_value': float(account.portfolio_value),
            'last_equity': float(account.last_equity),
            'status': account.status,
            'pattern_day_trader': account.pattern_day_trader
        }
    except Exception as e:
        st.error(f"Error fetching account: {e}")
        return None


def get_positions() -> List[Dict]:
    """Get current positions from Alpaca"""
    if not trading_client:
        return []
    try:
        positions = trading_client.get_all_positions()
        return [{
            'symbol': p.symbol,
            'qty': float(p.qty),
            'avg_entry_price': float(p.avg_entry_price),
            'current_price': float(p.current_price),
            'market_value': float(p.market_value),
            'unrealized_pl': float(p.unrealized_pl),
            'unrealized_plpc': float(p.unrealized_plpc),
            'unrealized_intraday_pl': float(p.unrealized_intraday_pl),
            'unrealized_intraday_plpc': float(p.unrealized_intraday_plpc),
        } for p in positions]
    except Exception as e:
        st.error(f"Error fetching positions: {e}")
        return []


def get_recent_orders(limit: int = 50) -> List[Dict]:
    """Get recent orders from Alpaca"""
    if not trading_client:
        return []
    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus
        
        request = GetOrdersRequest(
            status=QueryOrderStatus.ALL,
            limit=limit
        )
        orders = trading_client.get_orders(filter=request)
        
        return [{
            'id': o.id,
            'symbol': o.symbol,
            'side': o.side.value,
            'qty': float(o.qty),
            'type': o.type.value,
            'status': o.status.value,
            'filled_qty': float(o.filled_qty) if o.filled_qty else 0,
            'filled_avg_price': float(o.filled_avg_price) if o.filled_avg_price else 0,
            'created_at': o.created_at.isoformat(),
            'updated_at': o.updated_at.isoformat() if o.updated_at else None
        } for o in orders]
    except Exception as e:
        st.error(f"Error fetching orders: {e}")
        return []


# ============================================================================
# UI RENDERING
# ============================================================================

def render_header():
    """Render dashboard header"""
    st.title("📊 LOCAL TRADING DASHBOARD")
    st.caption("Terminal-style live monitoring | Connected to Alpaca API")
    st.divider()


def render_account_summary():
    """Render account metrics"""
    st.subheader("💰 ACCOUNT SUMMARY")
    
    account = get_account_info()
    if not account:
        st.warning("API keys not configured or Alpaca connection failed")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        equity = account['equity']
        last_equity = account['last_equity']
        daily_pnl = equity - last_equity
        daily_pnl_pct = (daily_pnl / last_equity * 100) if last_equity > 0 else 0
        st.metric("Portfolio Value", f"${equity:,.2f}", delta=f"{daily_pnl_pct:+.2f}%")
    
    with col2:
        cash = account['cash']
        cash_pct = (cash / equity * 100) if equity > 0 else 0
        st.metric("Cash", f"${cash:,.2f}", delta=f"{cash_pct:.1f}% liquid")
    
    with col3:
        st.metric("Buying Power", f"${account['buying_power']:,.2f}")
    
    with col4:
        daily_pnl_str = f"-${abs(daily_pnl):,.2f}" if daily_pnl < 0 else f"${daily_pnl:,.2f}"
        st.metric("Today P&L", daily_pnl_str, delta=f"{daily_pnl_pct:+.2f}%")
    
    st.divider()


def render_performance_charts():
    """Render MTD performance comparison and VIX chart"""
    st.header("📈 PERFORMANCE")
    
    try:
        # Get start of month
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        days_mtd = (now - start_of_month).days + 1
        
        # Fetch real SPY data from Polygon first to get reference timestamps
        spy_returns = []
        spy_dates = []
        spy_timestamps = []
        
        if POLYGON_API_KEY:
            try:
                # Format dates for API
                start_date = start_of_month.strftime('%Y-%m-%d')
                end_date = now.strftime('%Y-%m-%d')
                
                # Fetch SPY hourly data from Polygon
                url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/hour/{start_date}/{end_date}?adjusted=true&sort=asc&apiKey={POLYGON_API_KEY}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('results'):
                        spy_prices = [bar['c'] for bar in data['results']]  # close prices
                        spy_timestamps = [bar['t'] / 1000 for bar in data['results']]  # convert ms to seconds
                        
                        if spy_prices:
                            spy_start = spy_prices[0]
                            spy_dates = [datetime.fromtimestamp(ts) for ts in spy_timestamps]
                            spy_returns = [(price / spy_start - 1) * 100 for price in spy_prices]
            except Exception as e:
                st.warning(f"Could not fetch SPY data: {e}")
        
        # Get portfolio history from Alpaca API with same timeframe as SPY
        # Use specific day period to ensure < 30 days constraint
        portfolio_history = trading_client.get_portfolio_history(
            GetPortfolioHistoryRequest(
                period=f"{days_mtd}D",  # MTD period (always < 30 days)
                timeframe="1H"  # Hourly intervals matching SPY data
            )
        )
        
        # Process portfolio data
        portfolio_values = list(portfolio_history.equity) if portfolio_history.equity else []
        portfolio_timestamps = list(portfolio_history.timestamp) if portfolio_history.timestamp else []
        
        # Build portfolio returns aligned to SPY timestamps if available
        portfolio_returns = []
        
        if portfolio_values and portfolio_timestamps:
            # Filter to MTD and create lookup dict
            portfolio_dict = {}
            mtd_portfolio_values = []
            
            for i, ts in enumerate(portfolio_timestamps):
                dt = datetime.fromtimestamp(ts)
                if dt >= start_of_month:
                    portfolio_dict[ts] = portfolio_values[i]
                    mtd_portfolio_values.append(portfolio_values[i])
            
            # Get start value for return calculation
            if mtd_portfolio_values:
                start_value = mtd_portfolio_values[0]
                
                # If we have SPY timestamps, align portfolio data to them
                if spy_timestamps:
                    for spy_ts in spy_timestamps:
                        # Find closest portfolio timestamp
                        closest_ts = min(portfolio_dict.keys(), key=lambda x: abs(x - spy_ts), default=None)
                        if closest_ts and abs(closest_ts - spy_ts) < 7200:  # Within 2 hours
                            portfolio_returns.append((portfolio_dict[closest_ts] / start_value - 1) * 100)
                        else:
                            portfolio_returns.append(None)
                else:
                    # No SPY data, use portfolio timestamps directly
                    portfolio_returns = [(val / start_value - 1) * 100 for val in mtd_portfolio_values]
        
        # Use SPY dates as primary timeline if available
        if spy_dates and spy_returns:
            chart_dates = spy_dates
        else:
            # Fallback: use portfolio dates
            chart_dates = [datetime.fromtimestamp(ts) for ts in portfolio_timestamps if datetime.fromtimestamp(ts) >= start_of_month]
            if not chart_dates:
                chart_dates = [now]
                portfolio_returns = [0.0]
        
        # Ensure equal length by padding with None
        max_len = len(chart_dates)
        if len(portfolio_returns) < max_len:
            portfolio_returns.extend([None] * (max_len - len(portfolio_returns)))
        if len(spy_returns) < max_len:
            spy_returns.extend([None] * (max_len - len(spy_returns)))
        
        # Create single column for main chart
        st.subheader("MTD Performance Comparison")
        
        chart_data = pd.DataFrame({
            'Date': chart_dates,
            'Portfolio': portfolio_returns[:max_len],
            'SPY': spy_returns[:max_len]
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


def render_positions():
    """Render current positions table"""
    st.subheader("📈 CURRENT POSITIONS")
    
    positions = get_positions()
    
    if not positions:
        st.info("No open positions")
        return
    
    # Create DataFrame
    df = pd.DataFrame([{
        'Symbol': p['symbol'],
        'Qty': int(p['qty']),
        'Entry': f"${p['avg_entry_price']:.2f}",
        'Current': f"${p['current_price']:.2f}",
        'Value': f"${p['market_value']:,.2f}",
        'P&L': f"-${abs(p['unrealized_pl']):,.2f}" if p['unrealized_pl'] < 0 else f"${p['unrealized_pl']:,.2f}",
        'P&L%': f"{p['unrealized_plpc']*100:+.2f}%",
        'Today P&L': f"-${abs(p['unrealized_intraday_pl']):,.2f}" if p['unrealized_intraday_pl'] < 0 else f"${p['unrealized_intraday_pl']:,.2f}",
        'Today%': f"{p['unrealized_intraday_plpc']*100:+.2f}%"
    } for p in positions])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Position stats
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_value = sum(p['market_value'] for p in positions)
        st.metric("Total Position Value", f"${total_value:,.2f}")
    
    with col2:
        total_pl = sum(p['unrealized_pl'] for p in positions)
        winners = len([p for p in positions if p['unrealized_pl'] > 0])
        total_pl_str = f"-${abs(total_pl):,.2f}" if total_pl < 0 else f"${total_pl:,.2f}"
        st.metric("Total P&L", total_pl_str, delta=f"{winners}/{len(positions)} winners")
    
    with col3:
        avg_pl_pct = np.mean([p['unrealized_plpc'] * 100 for p in positions])
        st.metric("Avg P&L%", f"{avg_pl_pct:+.2f}%")
    
    st.divider()


def render_scanner_results():
    """Render scanner results"""
    st.subheader("🔍 MARKET SCANNER RESULTS")
    
    scan_data = load_scan_results()
    
    if not scan_data:
        st.info("No recent scan results. Run: python daily_scanner.py --mode scan")
        return
    
    # Scan metadata
    col1, col2, col3 = st.columns(3)
    
    with col1:
        timestamp = scan_data.get('timestamp', 'Unknown')
        st.caption(f"Last Scan: {timestamp}")
    
    with col2:
        regime_data = scan_data.get('market_regime', {})
        if isinstance(regime_data, dict):
            regime = regime_data.get('regime', 'Unknown')
        else:
            regime = str(regime_data) if regime_data else 'Unknown'
        st.caption(f"Market Regime: {regime}")
    
    with col3:
        hot_sectors = scan_data.get('hot_sectors', [])
        st.caption(f"Hot Sectors: {', '.join(hot_sectors[:3]) if hot_sectors else 'N/A'}")
    
    # Top scorers
    st.write("**Top 20 Opportunities**")
    scores = scan_data.get('top_scorers', [])[:20]
    
    if scores:
        df = pd.DataFrame([{
            'Rank': i+1,
            'Ticker': s['ticker'],
            'Score': f"{s['composite']:.1f}",
            'Momentum': f"{s['momentum']:.1f}",
            'Volatility': f"{s['volatility']:.1f}",
            'Rel Strength': f"{s['relative_strength']:.1f}",
            '30D Return': f"{s['return_30d']:+.1f}%",
            'Price': f"${s['price']:.2f}"
        } for i, s in enumerate(scores)])
        
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)
    
    st.divider()


def render_trading_logs():
    """Render Portfolio Manager logs"""
    st.subheader("🤖 PORTFOLIO MANAGER LOGS")
    
    logs = load_log_file('trading_automation_*.log', max_lines=30)
    
    if logs:
        log_text = ''.join(logs)
        st.text_area("Recent Activity", log_text, height=300)
    else:
        st.info("No trading logs yet. Run: python trading_automation.py --mode dry-run")
    
    st.divider()


def render_profit_taker_logs():
    """Render Profit Taker logs"""
    st.subheader("💎 PROFIT TAKER LOGS")
    
    logs = load_log_file('profit_taker_*.log', max_lines=30)
    
    if logs:
        log_text = ''.join(logs)
        st.text_area("Recent Activity", log_text, height=300)
    else:
        st.info("No profit taker logs. Run: python intraday_profit_taker.py --mode moderate")
    
    st.divider()


def render_recent_orders():
    """Render recent orders"""
    st.subheader("📋 RECENT ORDERS")
    
    orders = get_recent_orders(limit=20)
    
    if not orders:
        st.info("No recent orders")
        return
    
    df = pd.DataFrame([{
        'Time': datetime.fromisoformat(o['created_at'].replace('Z', '+00:00')).strftime('%m/%d %H:%M'),
        'Symbol': o['symbol'],
        'Side': o['side'].upper(),
        'Qty': int(o['qty']),
        'Status': o['status'].upper(),
        'Filled': f"{int(o['filled_qty'])}/{int(o['qty'])}",
        'Avg Price': f"${o['filled_avg_price']:.2f}" if o['filled_avg_price'] > 0 else 'N/A'
    } for o in orders])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.divider()


# ============================================================================
# MAIN APP
# ============================================================================

def main():
    st.set_page_config(
        page_title="Local Trading Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ CONTROLS")
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)
        
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.divider()
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    
    # Render sections
    render_header()
    render_account_summary()
    render_performance_charts()
    render_positions()
    render_scanner_results()
    render_trading_logs()
    render_profit_taker_logs()
    render_recent_orders()
    
    # Footer
    st.caption("🔒 Local dashboard with full API access | Not for public deployment")
    
    # Auto-refresh
    if auto_refresh:
        time.sleep(30)
        st.rerun()


if __name__ == '__main__':
    main()
