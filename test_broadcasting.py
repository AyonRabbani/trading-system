#!/usr/bin/env python3
"""
Test Event Broadcasting System
Sends test events to verify WebSocket server and viewer are working.
"""

import time
import sys
from event_broadcaster import get_broadcaster

def main():
    print("🧪 Testing Event Broadcasting System")
    print("=" * 60)
    
    # Initialize broadcaster
    print("\n1️⃣  Connecting to WebSocket server...")
    broadcaster = get_broadcaster(source="Test Script")
    time.sleep(2)  # Give it time to connect
    
    # Test different event types
    print("\n2️⃣  Broadcasting test events...")
    
    # Scanner event
    print("   📊 Sending scan event...")
    broadcaster.broadcast_event(
        event_type="scan",
        message="🔍 TEST: Market scan started",
        level="INFO",
        phase="test"
    )
    time.sleep(1)
    
    # Strategy event
    print("   🎯 Sending strategy event...")
    broadcaster.broadcast_event(
        event_type="strategy",
        message="🎯 TEST: Selected CORE strategy | NAV: $125,432.10",
        level="INFO",
        strategy_name="CORE",
        nav=125432.10
    )
    time.sleep(1)
    
    # Order event
    print("   📊 Sending order event...")
    broadcaster.broadcast_event(
        event_type="order",
        message="📊 TEST: BUY 100 NVDA (MARKET)",
        level="INFO",
        action="BUY",
        ticker="NVDA",
        quantity=100
    )
    time.sleep(1)
    
    # Profit event
    print("   💰 Sending profit event...")
    broadcaster.broadcast_event(
        event_type="profit",
        message="💰 TEST: PROFIT TAKEN: TSLA +5.2% ($1,247.50)",
        level="INFO",
        ticker="TSLA",
        gain_pct=5.2,
        profit_dollars=1247.50
    )
    time.sleep(1)
    
    # Rebalance event
    print("   ⚖️ Sending rebalance event...")
    broadcaster.broadcast_event(
        event_type="rebalance",
        message="⚖️ TEST: Portfolio rebalancing complete",
        level="INFO"
    )
    time.sleep(1)
    
    # Info event
    print("   ℹ️ Sending info event...")
    broadcaster.broadcast_event(
        event_type="info",
        message="ℹ️ TEST: System status check - all systems operational",
        level="INFO"
    )
    time.sleep(1)
    
    # Warning event
    print("   ⚠️ Sending warning event...")
    broadcaster.broadcast_event(
        event_type="warning",
        message="⚠️ TEST: Volatility spike detected in SPY",
        level="WARNING"
    )
    time.sleep(1)
    
    print("\n✅ Test complete! Check the dashboard viewer for events.")
    print("\nIf you see all 7 test events in the PM Activity Feed,")
    print("the broadcasting system is working correctly! 🎉")
    
    broadcaster.close()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
        sys.exit(0)
