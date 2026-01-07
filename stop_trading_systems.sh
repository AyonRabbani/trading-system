#!/bin/bash
# Stop All Trading Systems

echo "🛑 Stopping Trading System..."
echo ""

# Stop WebSocket server
if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null ; then
    echo "Stopping WebSocket server..."
    kill $(lsof -Pi :8765 -sTCP:LISTEN -t) 2>/dev/null
    echo "   ✅ WebSocket server stopped"
else
    echo "   ℹ️  WebSocket server not running"
fi

# Stop Streamlit
if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null ; then
    echo "Stopping Dashboard viewer..."
    kill $(lsof -Pi :8501 -sTCP:LISTEN -t) 2>/dev/null
    echo "   ✅ Dashboard viewer stopped"
else
    echo "   ℹ️  Dashboard viewer not running"
fi

# Stop any other related processes
echo "Cleaning up other processes..."
pkill -f "log_broadcast_server.py" 2>/dev/null
pkill -f "trading_dashboard_viewer.py" 2>/dev/null
pkill -f "daily_scanner.py" 2>/dev/null
pkill -f "trading_automation.py" 2>/dev/null
pkill -f "intraday_profit_taker.py" 2>/dev/null

echo ""
echo "✅ All systems stopped"
echo ""
echo "📊 To restart: ./start_trading_systems.sh"
