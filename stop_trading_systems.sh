#!/bin/bash
# Stop All Trading Systems

echo "🛑 Stopping all trading systems..."

# Stop WebSocket server
echo "Stopping WebSocket server..."
pkill -f "log_broadcast_server.py"

# Stop Streamlit viewer
echo "Stopping dashboard viewer..."
pkill -f "streamlit run trading_dashboard_viewer"

# Stop any running trading scripts
echo "Stopping trading scripts..."
pkill -f "daily_scanner.py"
pkill -f "trading_automation.py"
pkill -f "intraday_profit_taker.py"

echo "✅ All systems stopped"
