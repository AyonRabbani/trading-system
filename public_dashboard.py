#!/usr/bin/env python3
"""
Public Trading Dashboard
Read-only viewer for public deployment (Streamlit Cloud)
Matches local dashboard appearance but reads from JSON files only
No API keys - safe for public sharing
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import time


# ============================================================================
# DATA LOADING FUNCTIONS
# ============================================================================

def load_public_events() -> List[Dict]:
    """Load sanitized public events"""
    events_file = Path('public_events.json')
    if events_file.exists():
        try:
            with open(events_file, 'r') as f:
                data = json.load(f)
                return data.get('events', [])
        except Exception as e:
            st.error(f"Error loading events: {e}")
    return []


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


def extract_account_summary(events: List[Dict]) -> Optional[Dict]:
    """Extract account summary from events"""
    for event in reversed(events):
        metadata = event.get('metadata', {})
        if 'portfolio_value' in metadata:
            return {
                'portfolio_value': metadata.get('portfolio_value', 'N/A'),
                'positions_count': metadata.get('positions_count', 0),
                'avg_return': metadata.get('avg_return', 0),
                'timestamp': event.get('timestamp', 'Unknown')
            }
    return None


def extract_positions_from_events(events: List[Dict]) -> List[Dict]:
    """Extract position information from events"""
    positions = []
    
    # Find latest monitoring events with position details
    for event in reversed(events):
        if 'Monitoring' in event.get('message', ''):
            message = event.get('message', '')
            # Parse format like: "Monitoring 2 positions: QQQ +0.2%, SPY +0.1%"
            if ':' in message:
                pos_part = message.split(':', 1)[1].strip()
                pos_items = pos_part.split(',')
                
                for item in pos_items:
                    item = item.strip()
                    if ' ' in item:
                        parts = item.split()
                        if len(parts) >= 2:
                            symbol = parts[0]
                            pnl_str = parts[1]
                            try:
                                pnl = float(pnl_str.replace('%', '').replace('+', ''))
                                positions.append({
                                    'symbol': symbol,
                                    'pnl_pct': pnl,
                                    'timestamp': event.get('timestamp', '')
                                })
                            except:
                                pass
            
            if positions:
                break
    
    return positions


# ============================================================================
# UI RENDERING
# ============================================================================

def render_header():
    """Render dashboard header"""
    st.title("📊 PUBLIC TRADING DASHBOARD")
    st.caption("Read-only view | Data synced from local system")
    st.divider()


def render_account_summary(events: List[Dict]):
    """Render account metrics from events"""
    st.subheader("💰 ACCOUNT SUMMARY")
    
    summary = extract_account_summary(events)
    
    if not summary:
        st.warning("No recent portfolio data. System may be offline or syncing.")
        return
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Portfolio Value", summary['portfolio_value'])
    
    with col2:
        st.metric("Positions", summary['positions_count'])
    
    with col3:
        avg_return = summary.get('avg_return', 0)
        st.metric("Avg Return", f"{avg_return:+.1f}%")
    
    with col4:
        # Calculate time since last update
        timestamp = summary.get('timestamp', '')
        if timestamp:
            try:
                event_time = datetime.fromisoformat(timestamp.replace('Z', ''))
                age_minutes = (datetime.now() - event_time).total_seconds() / 60
                if age_minutes < 60:
                    status = f"🟢 Active ({age_minutes:.0f}m ago)"
                else:
                    status = "⚪ Idle"
            except:
                status = "Unknown"
        else:
            status = "Unknown"
        st.metric("Status", status)
    
    st.caption(f"Last updated: {timestamp[:19] if timestamp else 'Unknown'}")
    st.divider()


def render_positions(events: List[Dict]):
    """Render current positions from events"""
    st.subheader("📈 CURRENT POSITIONS")
    
    positions = extract_positions_from_events(events)
    
    if not positions:
        st.info("No position data available. Positions are updated when profit taker is monitoring.")
        return
    
    # Create DataFrame
    df = pd.DataFrame([{
        'Symbol': p['symbol'],
        'P&L%': f"{p['pnl_pct']:+.2f}%",
        'Status': '🟢 Monitored' if p['pnl_pct'] > 0 else '🔴 Watching',
        'Last Update': p['timestamp'][:19] if p['timestamp'] else 'N/A'
    } for p in positions])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Position stats
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Positions", len(positions))
    
    with col2:
        winners = len([p for p in positions if p['pnl_pct'] > 0])
        st.metric("Winning Positions", f"{winners}/{len(positions)}")
    
    with col3:
        if positions:
            avg_pnl = np.mean([p['pnl_pct'] for p in positions])
            st.metric("Avg P&L%", f"{avg_pnl:+.2f}%")
    
    st.divider()


def render_scanner_results():
    """Render market scanner results"""
    st.subheader("🔍 MARKET SCANNER RESULTS")
    
    scan_data = load_scan_results()
    
    if not scan_data:
        st.info("No scan results available yet.")
        return
    
    # Scan metadata
    col1, col2, col3 = st.columns(3)
    
    with col1:
        timestamp = scan_data.get('timestamp', 'Unknown')
        st.caption(f"Last Scan: {timestamp}")
    
    with col2:
        market_regime = scan_data.get('market_regime', {})
        if isinstance(market_regime, dict):
            regime = market_regime.get('regime', 'Unknown')
        else:
            regime = str(market_regime) if market_regime else 'Unknown'
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
            'Ticker': s.get('ticker', 'N/A'),
            'Score': f"{s.get('composite', 0):.1f}",
            'Momentum': f"{s.get('momentum', 0):.1f}",
            'Volatility': f"{s.get('volatility', 0):.1f}",
            'Rel Strength': f"{s.get('relative_strength', 0):.1f}",
            '30D Return': f"{s.get('return_30d', 0):+.1f}%",
            'Price': f"${s.get('price', 0):.2f}"
        } for i, s in enumerate(scores)])
        
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("No top scorers data available.")
    
    st.divider()


def render_trading_logs(events: List[Dict]):
    """Render Portfolio Manager activity from events"""
    st.subheader("🤖 PORTFOLIO MANAGER ACTIVITY")
    
    # Filter strategy and order events
    trading_events = [e for e in events if e.get('type') in ['strategy', 'order', 'rebalance']]
    
    if not trading_events:
        st.info("No trading activity recorded yet.")
        return
    
    # Display last 10 trading events
    log_lines = []
    for event in reversed(trading_events[-10:]):
        timestamp = event.get('timestamp', 'Unknown')[:19]
        message = event.get('message', '')
        log_lines.append(f"{timestamp} - {message}")
    
    log_text = '\n'.join(log_lines)
    st.text_area("Recent Activity", log_text, height=300)
    
    st.divider()


def render_profit_taker_logs(events: List[Dict]):
    """Render Profit Taker activity from events"""
    st.subheader("💎 PROFIT TAKER ACTIVITY")
    
    # Filter profit and portfolio monitoring events
    profit_events = [e for e in events if e.get('type') in ['profit', 'portfolio', 'info']]
    
    if not profit_events:
        st.info("No profit taker activity recorded yet.")
        return
    
    # Display last 10 profit events
    log_lines = []
    for event in reversed(profit_events[-10:]):
        timestamp = event.get('timestamp', 'Unknown')[:19]
        message = event.get('message', '')
        log_lines.append(f"{timestamp} - {message}")
    
    log_text = '\n'.join(log_lines)
    st.text_area("Recent Activity", log_text, height=300)
    
    st.divider()


def render_recent_orders(events: List[Dict]):
    """Render recent orders from events"""
    st.subheader("📋 RECENT ORDERS")
    
    # Filter order events
    order_events = [e for e in events if e.get('type') == 'order']
    
    if not order_events:
        st.info("No recent orders")
        return
    
    df = pd.DataFrame([{
        'Time': e.get('timestamp', 'Unknown')[:16],
        'Order': e.get('message', 'N/A'),
        'Source': e.get('source', 'Unknown')
    } for e in reversed(order_events[-20:])])
    
    st.dataframe(df, use_container_width=True, hide_index=True)
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
    
    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ SETTINGS")
        
        auto_refresh = st.checkbox("Auto-refresh", value=True)
        refresh_interval = st.slider("Refresh interval (seconds)", 10, 300, 60)
        
        st.divider()
        
        st.subheader("Display Sections")
        show_account = st.checkbox("Account Summary", value=True)
        show_positions = st.checkbox("Current Positions", value=True)
        show_scanner = st.checkbox("Scanner Results", value=True)
        show_trading = st.checkbox("Portfolio Manager", value=True)
        show_profit = st.checkbox("Profit Taker", value=True)
        show_orders = st.checkbox("Recent Orders", value=True)
        
        st.divider()
        
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.divider()
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        st.caption("⚠️ Public read-only view")
        st.caption("Data synced from local system")
    
    # Load data
    events = load_public_events()
    
    # Render sections
    render_header()
    
    if show_account:
        render_account_summary(events)
    
    if show_positions:
        render_positions(events)
    
    if show_scanner:
        render_scanner_results()
    
    if show_trading:
        render_trading_logs(events)
    
    if show_profit:
        render_profit_taker_logs(events)
    
    if show_orders:
        render_recent_orders(events)
    
    # Footer
    st.divider()
    st.caption(f"Dashboard refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.caption("🌐 Public read-only dashboard | No API keys | Data synced via GitHub")
    
    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == '__main__':
    main()

