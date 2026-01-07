#!/bin/bash
# Start All Trading Systems for Market Open
# This script launches the WebSocket server, viewer, and all trading scripts

cd "$(dirname "$0")"

echo "🚀 Starting Trading System - Market Open Workflow"
echo "=================================================="
echo ""

# Check if WebSocket server is already running
if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null ; then
    echo "⚠️  WebSocket server already running on port 8765"
else
    echo "📡 Starting WebSocket Broadcast Server..."
    python log_broadcast_server.py > logs/broadcast_server.log 2>&1 &
    BROADCAST_PID=$!
    echo "   PID: $BROADCAST_PID"
    sleep 2
fi

# Start Streamlit viewer in background
echo "📊 Starting Dashboard Viewer..."
streamlit run trading_dashboard_viewer.py --server.headless=true > logs/viewer.log 2>&1 &
VIEWER_PID=$!
echo "   PID: $VIEWER_PID"
echo "   Access at: http://localhost:8501"
sleep 3

echo ""
echo "✅ Core systems started!"
echo ""
echo "Now you can run trading scripts:"
echo ""
echo "1️⃣  Daily Scanner:"
echo "   python daily_scanner.py --mode scan --export scan_results.json"
echo ""
echo "2️⃣  Trading Automation:"
echo "   python trading_automation.py --mode live"
echo ""
echo "3️⃣  Profit Taker:"
echo "   python intraday_profit_taker.py --mode aggressive"
echo ""
echo "=================================================="
echo "Dashboard Viewer: http://localhost:8501"
echo "WebSocket Server: ws://localhost:8765"
echo ""
echo "To stop all systems: ./stop_trading_systems.sh"
echo "Or press Ctrl+C and run: pkill -f 'log_broadcast_server|streamlit'"
echo ""
