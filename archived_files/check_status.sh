#!/bin/bash
# Check status of all trading systems

echo "📊 Trading System Status Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Check WebSocket server
if lsof -Pi :8765 -sTCP:LISTEN -t >/dev/null ; then
    PID=$(lsof -Pi :8765 -sTCP:LISTEN -t)
    echo "🟢 WebSocket Server: RUNNING (PID: $PID)"
    echo "   URL: ws://localhost:8765"
else
    echo "🔴 WebSocket Server: STOPPED"
fi

echo ""

# Check Dashboard
if lsof -Pi :8501 -sTCP:LISTEN -t >/dev/null ; then
    PID=$(lsof -Pi :8501 -sTCP:LISTEN -t)
    echo "🟢 Dashboard Viewer: RUNNING (PID: $PID)"
    echo "   URL: http://localhost:8501"
else
    echo "🔴 Dashboard Viewer: STOPPED"
fi

echo ""

# Check for running trading scripts
echo "📈 Active Trading Scripts:"
if pgrep -f "daily_scanner.py" > /dev/null; then
    echo "   🟢 Scanner: RUNNING"
else
    echo "   ⚪ Scanner: not running"
fi

if pgrep -f "trading_automation.py" > /dev/null; then
    echo "   🟢 Trading Bot: RUNNING"
else
    echo "   ⚪ Trading Bot: not running"
fi

if pgrep -f "intraday_profit_taker.py" > /dev/null; then
    echo "   🟢 Profit Taker: RUNNING"
else
    echo "   ⚪ Profit Taker: not running"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
