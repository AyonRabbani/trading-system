#!/bin/bash
# start_all_services.sh - Clean startup with duplicate prevention

cd "$(dirname "$0")"

echo "========================================================================="
echo "TRADING SYSTEM - CLEAN START"
echo "========================================================================="
echo ""

# Step 1: Stop all existing processes
echo "🧹 Step 1: Cleaning up existing processes..."
if [ -f service_pids.txt ]; then
    while IFS='=' read -r name pid; do
        if ps -p $pid > /dev/null 2>&1; then
            echo "  Stopping $name (PID: $pid)..."
            kill $pid 2>/dev/null
        fi
    done < service_pids.txt
    rm -f service_pids.txt
fi

# Kill any stranded processes by name
echo "  Checking for stranded processes..."
pkill -f "log_broadcast_server.py" 2>/dev/null
pkill -f "local_dashboard.py" 2>/dev/null
pkill -f "sync_to_cloud.sh" 2>/dev/null
pkill -f "intraday_profit_taker.py" 2>/dev/null
pkill -f "update_dashboard_state.py" 2>/dev/null
pkill -f "pm_scheduler.sh" 2>/dev/null
pkill -f "pre_market_prep.py" 2>/dev/null

sleep 2
echo "  ✓ Cleanup complete"
echo ""

# Step 2: Start services
echo "🚀 Step 2: Starting services..."
> service_pids.txt

# 1. Log Broadcast Server
echo "  [1/7] Starting Log Broadcast Server..."
python log_broadcast_server.py > /dev/null 2>&1 &
echo "broadcast=$!" >> service_pids.txt
sleep 1

# 2. Local Dashboard
echo "  [2/7] Starting Local Dashboard (http://localhost:8501)..."
streamlit run local_dashboard.py --server.port 8501 --server.headless true > /dev/null 2>&1 &
echo "dashboard=$!" >> service_pids.txt
sleep 2

# 3. GitHub Sync
echo "  [3/7] Starting GitHub Auto-Sync..."
bash ./sync_to_cloud.sh --watch --interval 30 > /dev/null 2>&1 &
echo "github_sync=$!" >> service_pids.txt
sleep 1

# 4. Profit Taker
echo "  [4/7] Starting Intraday Profit Taker..."
python intraday_profit_taker.py --mode aggressive > /dev/null 2>&1 &
echo "profit_taker=$!" >> service_pids.txt
sleep 1

# 5. Dashboard State Updater
echo "  [5/7] Starting Dashboard State Updater..."
bash -c 'while true; do python update_dashboard_state.py > /dev/null 2>&1; sleep 60; done' &
echo "dashboard_updater=$!" >> service_pids.txt
sleep 1

# 6. Portfolio Manager Scheduler
echo "  [6/7] Starting Portfolio Manager Scheduler..."
bash pm_scheduler.sh &
echo "pm_scheduler=$!" >> service_pids.txt
sleep 1

# 7. Pre-Market Prep Scheduler
echo "  [7/7] Starting Pre-Market Prep Scheduler..."
python pre_market_prep.py --daemon &
echo "premarket_scheduler=$!" >> service_pids.txt
sleep 1

echo "  ✓ All services started"
echo ""

# Step 3: Verify all services
echo "✅ Step 3: Verifying services..."
all_running=true
while IFS='=' read -r name pid; do
    if ps -p $pid > /dev/null 2>&1; then
        echo "  ✓ $name (PID: $pid)"
    else
        echo "  ✗ $name FAILED TO START"
        all_running=false
    fi
done < service_pids.txt

echo ""
if [ "$all_running" = true ]; then
    echo "========================================================================="
    echo "✅ ALL SERVICES RUNNING"
    echo "========================================================================="
    echo ""
    echo "📊 Dashboard: http://localhost:8501"
    echo "📝 PM Logs: tail -f logs/pm_scheduler.log"
    echo "🛑 Stop All: ./stop_all_services.sh"
    echo ""
    echo "Services:"
    echo "  • Log Broadcast Server (WebSocket)"
    echo "  • Local Dashboard (Streamlit)"
    echo "  • GitHub Auto-Sync (Every 30s)"
    echo "  • Profit Taker (Aggressive mode)"
    echo "  • Dashboard Updater (Every 60s)"
    echo "  • PM Scheduler (Every 15 min during market hours)"
    echo "  • Pre-Market Prep (8 PM prepare, 9 AM validate/execute)"
    echo ""
else
    echo "========================================================================="
    echo "⚠️  SOME SERVICES FAILED - Check logs/"
    echo "========================================================================="
    echo ""
fi
