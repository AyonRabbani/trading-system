#!/bin/bash

# Restart All Trading System Services
# Single command to kill and restart everything

set -e

cd "$(dirname "$0")"

echo "=================================="
echo "TRADING SYSTEM RESTART"
echo "=================================="
echo ""

# 1. Kill all existing processes
echo "🛑 Stopping all services..."
pkill -f "streamlit.*local_dashboard" 2>/dev/null || true
pkill -f "sync_to_cloud" 2>/dev/null || true
pkill -f "intraday_profit_taker" 2>/dev/null || true
pkill -f "log_broadcast_server" 2>/dev/null || true
sleep 2
echo "✅ All services stopped"
echo ""

# 2. Create logs directory
mkdir -p logs

# 3. Start WebSocket broadcast server
echo "📡 Starting WebSocket broadcast server..."
nohup python log_broadcast_server.py > logs/broadcast_server.log 2>&1 &
BROADCAST_PID=$!
sleep 1
echo "✅ Broadcast server started (PID: $BROADCAST_PID)"

# 4. Start local dashboard
echo "📊 Starting local dashboard..."
nohup streamlit run local_dashboard.py --server.port 8501 --server.headless true > logs/local_dashboard.log 2>&1 &
DASHBOARD_PID=$!
sleep 2
echo "✅ Local dashboard started (PID: $DASHBOARD_PID)"
echo "   URL: http://localhost:8501"

# 5. Start GitHub sync
echo "🔄 Starting GitHub sync..."
nohup ./sync_to_cloud.sh --watch --interval 30 > logs/cloud_sync.log 2>&1 &
SYNC_PID=$!
sleep 1
echo "✅ GitHub sync started (PID: $SYNC_PID)"

# 6. Start profit taker
echo "🎯 Starting profit taker (aggressive mode)..."
nohup python intraday_profit_taker.py --mode aggressive > logs/profit_taker_$(date +%Y%m%d_%H%M%S).log 2>&1 &
PROFIT_PID=$!
sleep 1
echo "✅ Profit taker started (PID: $PROFIT_PID)"

# 7. Start dashboard state updater (updates public dashboard data every 60s)
echo "🔄 Starting dashboard state updater..."
nohup bash -c 'while true; do python update_dashboard_state.py > /dev/null 2>&1; sleep 60; done' > logs/dashboard_updater.log 2>&1 &
UPDATER_PID=$!
sleep 1
echo "✅ Dashboard updater started (PID: $UPDATER_PID)"

# Save PIDs
echo "$BROADCAST_PID" > .trading_pids
echo "$DASHBOARD_PID" >> .trading_pids
echo "$SYNC_PID" >> .trading_pids
echo "$PROFIT_PID" >> .trading_pids
echo "$UPDATER_PID" >> .trading_pids

echo ""
echo "=================================="
echo "✅ ALL SERVICES RUNNING"
echo "=================================="
echo ""
echo "📊 Local Dashboard: http://localhost:8501"
echo "📡 WebSocket: ws://localhost:8765"
echo "🔄 GitHub Sync: Every 30 seconds"
echo "🔄 Dashboard Updater: Every 60 seconds"
echo "🎯 Profit Taker: Aggressive mode"
echo ""
echo "PIDs saved to .trading_pids"
echo ""
echo "To stop all: pkill -f 'streamlit.*local_dashboard|sync_to_cloud|intraday_profit_taker|log_broadcast_server|update_dashboard_state'"
echo ""
