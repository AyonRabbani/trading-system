#!/usr/bin/env python3
"""
Public Trading Dashboard
Read-only viewer for public deployment (Streamlit Cloud)
Reads from public_events.json and scan_results.json synced from local
No API keys - safe for public sharing
"""

import streamlit as st
import pandas as pd
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


# ============================================================================
# UI RENDERING
# ============================================================================

def render_header():
    """Render dashboard header"""
    st.title("📊 PUBLIC TRADING DASHBOARD")
    st.caption("Read-only view | Data synced from local system")
    st.divider()


def render_system_status(events: List[Dict]):
    """Render system status based on recent events"""
    st.subheader("🟢 SYSTEM STATUS")
    
    if not events:
        st.warning("No events received. System may be offline.")
        return
    
    # Count recent events by source
    now = datetime.now()
    recent_cutoff = 3600  # 1 hour
    
    scanner_active = False
    trader_active = False
    profit_taker_active = False
    
    for event in events[-50:]:  # Check last 50 events
        try:
            event_time = datetime.fromisoformat(event['timestamp'].replace('Z', ''))
            age_seconds = (now - event_time).total_seconds()
            
            if age_seconds < recent_cutoff:
                source = event.get('source', '').lower()
                if 'scanner' in source:
                    scanner_active = True
                elif 'trading' in source or 'automation' in source:
                    trader_active = True
                elif 'profit' in source:
                    profit_taker_active = True
        except:
            continue
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        status = "🟢 Active" if scanner_active else "⚪ Idle"
        st.metric("Market Scanner", status)
    
    with col2:
        status = "🟢 Active" if trader_active else "⚪ Idle"
        st.metric("Trading Bot", status)
    
    with col3:
        status = "🟢 Active" if profit_taker_active else "⚪ Idle"
        st.metric("Profit Taker", status)
    
    st.divider()


def render_event_feed(events: List[Dict], event_filter: Optional[List[str]] = None):
    """Render activity feed"""
    st.subheader("📡 ACTIVITY FEED")
    
    if not events:
        st.info("No activity yet. System is offline or data hasn't synced.")
        st.caption("This dashboard updates when the local system runs and syncs to GitHub.")
        return
    
    # Filter events
    if event_filter:
        filtered = [e for e in events if e.get('type') in event_filter]
    else:
        filtered = events
    
    st.caption(f"Showing {len(filtered)} events (last {len(events)} total)")
    
    # Display events
    for event in reversed(filtered[-30:]):  # Show last 30 events, newest first
        timestamp = event.get('timestamp', 'Unknown')[:19]
        source = event.get('source', 'Unknown')
        message = event.get('message', '')
        event_type = event.get('type', 'info')
        
        # Format display
        icon_map = {
            'scan': '🔍',
            'strategy': '🎯',
            'order': '📝',
            'profit': '💰',
            'rebalance': '⚖️',
            'info': 'ℹ️',
            'warning': '⚠️',
            'error': '❌'
        }
        icon = icon_map.get(event_type, '📊')
        
        with st.container():
            col1, col2 = st.columns([1, 20])
            
            with col1:
                st.write(icon)
            
            with col2:
                st.caption(f"{timestamp} | {source}")
                st.write(message)
            
            st.divider()
    
    st.divider()


def render_scanner_results():
    """Render market scanner results"""
    st.subheader("🔍 MARKET SCANNER")
    
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
    st.write("**Top 15 Opportunities**")
    scores = scan_data.get('top_scorers', [])[:15]
    
    if scores:
        df = pd.DataFrame([{
            'Rank': i+1,
            'Ticker': s.get('ticker', 'N/A'),
            'Score': f"{s.get('composite', 0):.1f}",
            'Momentum': f"{s.get('momentum', 0):.1f}",
            '30D Return': f"{s.get('return_30d', 0):+.1f}%",
            'Price': f"${s.get('price', 0):.2f}"
        } for i, s in enumerate(scores)])
        
        st.dataframe(df, use_container_width=True, hide_index=True, height=350)
    else:
        st.info("No top scorers data available.")
    
    st.divider()


def render_portfolio_summary(events: List[Dict]):
    """Extract and display portfolio summary from events"""
    st.subheader("💼 PORTFOLIO SUMMARY")
    
    # Extract portfolio metrics from events
    portfolio_events = [e for e in events if e.get('type') in ['strategy', 'portfolio', 'info']]
    
    if portfolio_events:
        # Latest strategy
        strategy_events = [e for e in portfolio_events if e.get('type') == 'strategy']
        if strategy_events:
            latest = strategy_events[-1]
            st.write(f"**Latest Strategy:** {latest.get('message', 'N/A')}")
            st.caption(f"Selected at: {latest.get('timestamp', 'Unknown')[:19]}")
        
        # Current positions from profit taker events
        position_events = [e for e in events if 'Monitoring' in e.get('message', '') and 'positions' in e.get('message', '')]
        if position_events:
            latest_position = position_events[-1]
            st.write(f"**Active Positions:** {latest_position.get('message', 'N/A')}")
            st.caption(f"Updated: {latest_position.get('timestamp', 'Unknown')[:19]}")
        
        # Portfolio metrics from events metadata
        for event in reversed(portfolio_events[-5:]):
            metadata = event.get('metadata', {})
            if 'portfolio_value' in metadata or 'total_return' in metadata:
                col1, col2, col3 = st.columns(3)
                with col1:
                    if 'portfolio_value' in metadata:
                        st.metric("Portfolio Value", f"~${metadata['portfolio_value']}")
                with col2:
                    if 'total_return' in metadata:
                        st.metric("Total Return", f"{metadata['total_return']:.1f}%")
                with col3:
                    if 'positions_count' in metadata:
                        st.metric("Positions", metadata['positions_count'])
                break
    else:
        st.info("No recent portfolio activity recorded.")
    
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
        st.header("⚙️ FILTERS")
        
        show_all = st.checkbox("Show all events", value=True)
        
        if not show_all:
            event_filter = st.multiselect(
                "Event types",
                options=['scan', 'strategy', 'order', 'profit', 'rebalance', 'info', 'warning', 'error'],
                default=['scan', 'strategy', 'order', 'profit']
            )
        else:
            event_filter = None
        
        st.divider()
        
        auto_refresh = st.checkbox("Auto-refresh (30s)", value=False)
        
        if st.button("🔄 Refresh Now"):
            st.rerun()
        
        st.divider()
        st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")
        
        st.divider()
        st.caption("⚠️ Public dashboard")
        st.caption("Data is sanitized for privacy")
    
    # Load data
    events = load_public_events()
    
    # Render sections
    render_header()
    render_system_status(events)
    render_event_feed(events, event_filter)
    render_scanner_results()
    render_portfolio_summary(events)
    
    # Footer
    st.divider()
    st.caption("🌐 Public read-only dashboard | No API keys | Data synced from local system via GitHub")
    st.caption("To run locally with full features: git clone https://github.com/AyonRabbani/trading-system.git")
    
    # Auto-refresh
    if auto_refresh:
        time.sleep(30)
        st.rerun()


if __name__ == '__main__':
    main()
