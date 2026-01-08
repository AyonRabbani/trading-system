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

# Alpaca imports
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load environment
from dotenv import load_dotenv
load_dotenv()

# Initialize Alpaca clients
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

trading_client = None
if ALPACA_API_KEY and ALPACA_SECRET_KEY:
    trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)


def export_dashboard_state():
    """Export complete dashboard state to JSON for public dashboard sync"""
    try:
        state = {
            'timestamp': datetime.now().isoformat(),
            'account': get_account_info(),
            'positions': get_positions(),
            'orders': get_recent_orders(limit=20),
            'scan_results': load_scan_results()
        }
        
        with open('dashboard_state.json', 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        return True
    except Exception as e:
        print(f"Error exporting dashboard state: {e}")
        return False


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
        # Get account data
        account = trading_client.get_account()
        equity = float(account.equity)
        
        # Initialize data client
        data_client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        
        # Get start of month
        now = datetime.now()
        start_of_month = datetime(now.year, now.month, 1)
        
        # Fetch SPY and VIX data for MTD
        request = StockBarsRequest(
            symbol_or_symbols=["SPY", "VIX"],
            start=start_of_month,
            timeframe=TimeFrame.Day
        )
        bars = data_client.get_stock_bars(request)
        
        # Process SPY data
        spy_bars = bars["SPY"]
        spy_prices = [bar.close for bar in spy_bars]
        spy_dates = [bar.timestamp for bar in spy_bars]
        
        if spy_prices:
            spy_start = spy_prices[0]
            spy_returns = [(price / spy_start - 1) * 100 for price in spy_prices]
        else:
            spy_returns = []
            spy_dates = []
        
        # Process VIX data
        vix_bars = bars.get("VIX", [])
        vix_values = [bar.close for bar in vix_bars] if vix_bars else []
        vix_dates = [bar.timestamp for bar in vix_bars] if vix_bars else []
        
        # Get portfolio history from pm_state.json
        portfolio_returns = []
        portfolio_dates = []
        
        if os.path.exists('pm_state.json'):
            with open('pm_state.json', 'r') as f:
                pm_state = json.load(f)
                if 'equity_history' in pm_state:
                    history = pm_state['equity_history']
                    # Filter to MTD only
                    mtd_history = {k: v for k, v in history.items() if datetime.fromisoformat(k) >= start_of_month}
                    
                    if mtd_history:
                        start_equity = list(mtd_history.values())[0]
                        for date_str, eq in mtd_history.items():
                            portfolio_dates.append(datetime.fromisoformat(date_str))
                            portfolio_returns.append((eq / start_equity - 1) * 100)
        
        # If no history, use current equity as single point
        if not portfolio_returns:
            portfolio_dates = [now]
            portfolio_returns = [0.0]  # No gain/loss if no history
        
        # Create two columns for charts
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("MTD Performance Comparison")
            
            # Create DataFrame for plotting
            max_len = max(len(spy_returns), len(portfolio_returns))
            
            chart_data = pd.DataFrame({
                'Date': spy_dates[:max_len] if len(spy_dates) >= max_len else portfolio_dates[:max_len],
                'Portfolio': portfolio_returns + [None] * (max_len - len(portfolio_returns)) if len(portfolio_returns) < max_len else portfolio_returns[:max_len],
                'SPY': spy_returns + [None] * (max_len - len(spy_returns)) if len(spy_returns) < max_len else spy_returns[:max_len]
            }).set_index('Date')
            
            st.line_chart(chart_data, use_container_width=True, height=300)
            
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
        
        with col2:
            st.subheader("VIX")
            
            if vix_values:
                vix_df = pd.DataFrame({
                    'Date': vix_dates,
                    'VIX': vix_values
                }).set_index('Date')
                
                st.line_chart(vix_df, use_container_width=True, height=300, color="#ff4444")
                
                current_vix = vix_values[-1]
                avg_vix = np.mean(vix_values)
                st.metric("Current VIX", f"{current_vix:.2f}")
                st.metric("MTD Avg", f"{avg_vix:.2f}")
            else:
                st.info("VIX data unavailable")
    
    except Exception as e:
        st.error(f"Error loading performance charts: {e}")
    
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
    
    # Export dashboard state for public sync
    export_dashboard_state()
    
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
