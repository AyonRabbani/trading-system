#!/bin/bash
# Start All Trading Systems for Market Open
# This script launches the WebSocket server, viewer, and all trading scripts

cd "$(dirname "$0")"

echo "🚀 Starting Trading System - Market Open Workflow"
echo "=================================================="
echo ""

# Create logs directory if it doesn't exist
mkdir -p logs

# Check if WebSocket server is already running
if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  WebSocket server already running on port 8765"
    BROADCAST_PID=$(lsof -Pi :8765 -sTCP:LISTEN -t)
else
    echo "📡 Starting WebSocket Broadcast Server..."
    python log_broadcast_server.py > logs/broadcast_server.log 2>&1 &
    BROADCAST_PID=$!
    echo "   PID: $BROADCAST_PID"
    sleep 2
    
    # Verify it started
    if ps -p $BROADCAST_PID > /dev/null; then
        echo "   ✅ Server running"
    else
        echo "   ❌ Server failed to start - check logs/broadcast_server.log"
        exit 1
    fi
fi

# Check if Streamlit is already running
if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  Dashboard viewer already running on port 8501"
    VIEWER_PID=$(lsof -Pi :8501 -sTCP:LISTEN -t)
else
    echo "📊 Starting Dashboard Viewer..."
    streamlit run trading_dashboard_viewer.py --server.headless=true > logs/viewer.log 2>&1 &
    VIEWER_PID=$!
    echo "   PID: $VIEWER_PID"
    sleep 5
    
    # Verify it started
    if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null ; then
        echo "   ✅ Dashboard running at http://localhost:8501"
    else
        echo "   ❌ Dashboard failed to start - check logs/viewer.log"
        exit 1
    fi
fi

echo ""
echo "✅ Core systems started!"
echo ""
echo "📋 Running Services:"
echo "   • WebSocket Server (PID: $BROADCAST_PID) - ws://localhost:8765"
echo "   • Dashboard Viewer (PID: $VIEWER_PID) - http://localhost:8501"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📖 NEXT STEPS - Run Your Trading Scripts:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "1️⃣  Daily Scanner (Run once at market open):"
echo "   python daily_scanner.py --mode scan --export scan_results.json"
echo ""
echo "2️⃣  Trading Automation (Run once to place orders):"
echo "   python trading_automation.py --mode live"
echo ""
echo "3️⃣  Profit Taker (Runs continuously until market close):"
echo "   python intraday_profit_taker.py --mode aggressive"
echo ""
echo "4️⃣  Auto-Sync to Cloud (Optional - syncs every 60s):"
echo "   ./sync_to_cloud.sh --watch"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🛑 TO STOP:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   ./stop_trading_systems.sh"
echo ""
echo "📊 MONITORING:"
echo "   Open http://localhost:8501 in your browser"
echo "   Check 'PM Activity Feed' tab for real-time events"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✨ Press Ctrl+C to exit this terminal (systems keep running)"
echo ""

# Keep terminal open and show status
echo "Monitoring system status (refreshes every 10s)..."
echo "Press Ctrl+C to exit monitoring (systems will continue running)"
echo ""

while true; do
    # Check if processes are still running
    if ps -p $BROADCAST_PID > /dev/null 2>&1; then
        BROADCAST_STATUS="🟢 Running"
    else
        BROADCAST_STATUS="🔴 Stopped"
    fi
    
    if ps -p $VIEWER_PID > /dev/null 2>&1; then
        VIEWER_STATUS="🟢 Running"
    else
        VIEWER_STATUS="🔴 Stopped"
    fi
    
    # Clear line and print status
    echo -ne "\r[$(date '+%H:%M:%S')] WebSocket: $BROADCAST_STATUS | Dashboard: $VIEWER_STATUS"
    
    sleep 10
done
