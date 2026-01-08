#!/bin/bash
# stop_all_services.sh - Clean shutdown

cd "$(dirname "$0")"

echo "========================================================================="
echo "TRADING SYSTEM - STOPPING ALL SERVICES"
echo "========================================================================="
echo ""

if [ -f service_pids.txt ]; then
    while IFS='=' read -r name pid; do
        if ps -p $pid > /dev/null 2>&1; then
            echo "  Stopping $name (PID: $pid)..."
            kill $pid 2>/dev/null
        fi
    done < service_pids.txt
    rm -f service_pids.txt
fi

# Cleanup any stranded processes
echo "  Cleaning up stranded processes..."
pkill -f "log_broadcast_server.py" 2>/dev/null
pkill -f "local_dashboard.py" 2>/dev/null
pkill -f "sync_to_cloud.sh" 2>/dev/null
pkill -f "intraday_profit_taker.py" 2>/dev/null
pkill -f "update_dashboard_state.py" 2>/dev/null
pkill -f "pm_scheduler.sh" 2>/dev/null
pkill -f "pre_market_prep.py" 2>/dev/null

sleep 2

echo ""
echo "✅ All services stopped"
echo ""
