#!/bin/bash

# Complete Trading Workflow
# Runs: Scanner → Portfolio Manager → Rebalancing → Profit Taker

set -e

cd "$(dirname "$0")"

echo "========================================================================"
echo "DAILY TRADING WORKFLOW"
echo "========================================================================"
echo ""

# Parse arguments
DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "⚠️  DRY RUN MODE - No orders will be placed"
    echo ""
fi

# Create logs directory
mkdir -p logs

# Step 1: Run Scanner
echo "========================================================================"
echo "STEP 1/4: DAILY SCANNER"
echo "========================================================================"
echo ""
echo "🔍 Scanning market for opportunities..."
echo "   - Analyzing 110+ tickers across sectors"
echo "   - Calculating momentum, volatility, breakout scores"
echo "   - Assigning 10 tickers to each tier (CORE, SPEC, ASYM)"
echo ""

python daily_scanner.py --export scan_results.json

if [ ! -f "scan_results.json" ]; then
    echo "❌ ERROR: Scanner failed to create scan_results.json"
    exit 1
fi

echo ""
echo "✅ Scanner complete - Results saved to scan_results.json"
echo ""

# Display scan results summary
echo "📊 SCAN RESULTS:"
python -c "
import json
with open('scan_results.json') as f:
    data = json.load(f)
    buckets = data.get('dynamic_buckets', {})
    print(f\"   CORE ({len(buckets.get('CORE', []))}): {', '.join(buckets.get('CORE', [])[:5])}...\")
    print(f\"   SPEC ({len(buckets.get('SPECULATIVE', []))}): {', '.join(buckets.get('SPECULATIVE', [])[:5])}...\")
    print(f\"   ASYM ({len(buckets.get('ASYMMETRIC', []))}): {', '.join(buckets.get('ASYMMETRIC', [])[:5])}...\")
    print(f\"   Regime: {data.get('market_regime', 'UNKNOWN')}\")
"
echo ""
sleep 2

# Step 2: Run Portfolio Manager
echo "========================================================================"
echo "STEP 2/4: PORTFOLIO MANAGER"
echo "========================================================================"
echo ""
echo "🧠 Running strategy backtests..."
echo "   - BUY_HOLD: SPY/QQQ baseline"
echo "   - TACTICAL: Rotate between ETFs and benchmarks"
echo "   - SPEC: Tactical + 15% speculative stocks"
echo "   - ASYM: 3-tier risk-weighted allocation"
echo ""

if [ "$DRY_RUN" = true ]; then
    python trading_automation.py --dry-run 2>&1 | tee logs/trading_workflow_$(date +%Y%m%d_%H%M%S).log
else
    python trading_automation.py 2>&1 | tee logs/trading_workflow_$(date +%Y%m%d_%H%M%S).log
fi

PM_EXIT_CODE=$?

if [ $PM_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ ERROR: Portfolio Manager failed (exit code: $PM_EXIT_CODE)"
    echo "   Check logs/trading_workflow_*.log for details"
    exit 1
fi

echo ""
echo "✅ Portfolio Manager complete"
echo ""
sleep 2

# Step 3: Verify execution
echo "========================================================================"
echo "STEP 3/4: VERIFY EXECUTION"
echo "========================================================================"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "⚠️  DRY RUN - No orders were placed"
    echo "   Review the log to see what WOULD have been executed"
else
    echo "🔍 Checking order status..."
    
    # Quick Python check for recent orders
    python -c "
import os
import requests
from datetime import datetime, timedelta

headers = {
    'APCA-API-KEY-ID': os.getenv('APCA_API_KEY_ID'),
    'APCA-API-SECRET-KEY': os.getenv('APCA_API_SECRET_KEY')
}
base_url = os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')

try:
    # Get orders from last hour
    after = (datetime.now() - timedelta(hours=1)).isoformat() + 'Z'
    resp = requests.get(f'{base_url}/v2/orders', headers=headers, params={'after': after}, timeout=10)
    orders = resp.json()
    
    if isinstance(orders, list) and len(orders) > 0:
        print(f'   ✅ {len(orders)} orders placed in last hour')
        for order in orders[:5]:  # Show first 5
            status = order.get('status', 'unknown')
            side = order.get('side', '?')
            qty = order.get('qty', '?')
            symbol = order.get('symbol', '?')
            print(f'      {symbol}: {side.upper()} {qty} shares - {status}')
        if len(orders) > 5:
            print(f'      ... and {len(orders) - 5} more')
    else:
        print('   ℹ️  No orders placed in last hour (may be cooldown or no rebalance needed)')
except Exception as e:
    print(f'   ⚠️  Could not verify orders: {e}')
" || echo "   ⚠️  Could not verify orders"
fi

echo ""
sleep 2

# Step 4: Start/Restart Profit Taker
echo "========================================================================"
echo "STEP 4/4: PROFIT TAKER"
echo "========================================================================"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "⚠️  DRY RUN - Skipping profit taker activation"
else
    echo "🎯 Restarting profit taker with current positions..."
    
    # Kill existing profit taker
    pkill -f "intraday_profit_taker" 2>/dev/null || true
    sleep 2
    
    # Start new profit taker
    nohup python intraday_profit_taker.py --mode aggressive > logs/profit_taker_$(date +%Y%m%d_%H%M%S).log 2>&1 &
    PROFIT_PID=$!
    sleep 2
    
    # Check if it started successfully
    if ps -p $PROFIT_PID > /dev/null; then
        echo "✅ Profit taker started (PID: $PROFIT_PID)"
        
        # Show what it's monitoring
        sleep 1
        tail -10 logs/profit_taker_*.log | grep -E "Found|Monitoring|positions" | head -5 || true
    else
        echo "⚠️  Profit taker exited (market may be closed)"
        tail -5 logs/profit_taker_*.log
    fi
fi

echo ""
echo "========================================================================"
echo "✅ TRADING WORKFLOW COMPLETE"
echo "========================================================================"
echo ""

if [ "$DRY_RUN" = true ]; then
    echo "📋 NEXT STEPS (DRY RUN):"
    echo "   1. Review logs/trading_workflow_*.log"
    echo "   2. Verify strategy selection and order calculations"
    echo "   3. Run without --dry-run flag to execute live"
else
    echo "📋 SUMMARY:"
    echo "   ✅ Scanner: scan_results.json updated"
    echo "   ✅ Portfolio Manager: Strategy selected and executed"
    echo "   ✅ Profit Taker: Monitoring active positions"
    echo ""
    echo "📊 Monitor status:"
    echo "   - Local Dashboard: http://localhost:8501"
    echo "   - Public Dashboard: https://your-streamlit-app.streamlit.app"
    echo "   - Logs: logs/trading_workflow_*.log"
fi

echo ""
echo "To run monitoring services: ./restart_all.sh"
echo "To stop profit taker: pkill -f intraday_profit_taker"
echo ""
