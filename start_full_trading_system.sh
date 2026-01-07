#!/bin/bash

# ============================================================================
# FULL TRADING SYSTEM STARTUP
# Starts all components in correct order with monitoring
# ============================================================================

echo "🚀 STARTING COMPLETE TRADING SYSTEM"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Change to script directory
cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# PID tracking
PIDS_FILE=".trading_pids"
rm -f "$PIDS_FILE"

# ============================================================================
# STEP 1: Start WebSocket Broadcast Server
# ============================================================================
echo -e "${BLUE}[1/5]${NC} Starting WebSocket Broadcast Server..."

# Check if already running
BROADCAST_PID=$(pgrep -f "log_broadcast_server.py" | head -1)

if [ -n "$BROADCAST_PID" ]; then
    echo -e "   ${YELLOW}⚡${NC} Already running (PID: $BROADCAST_PID)"
    echo "$BROADCAST_PID" >> "$PIDS_FILE"
else
    python log_broadcast_server.py > logs/broadcast_server.log 2>&1 &
    BROADCAST_PID=$!
    echo "$BROADCAST_PID" >> "$PIDS_FILE"
    sleep 2
    
    if ps -p $BROADCAST_PID > /dev/null; then
        echo -e "   ${GREEN}✓${NC} WebSocket Server started (PID: $BROADCAST_PID)"
    else
        echo -e "   ${RED}✗${NC} Failed to start WebSocket Server"
        echo "   Continuing anyway..."
    fi
fi
echo "   📡 ws://localhost:8765"
echo ""

# ============================================================================
# STEP 2: Start Local Dashboard
# ============================================================================
echo -e "${BLUE}[2/5]${NC} Starting Local Dashboard..."

# Check if already running
DASHBOARD_PID=$(pgrep -f "streamlit.*local_dashboard.py" | head -1)

if [ -n "$DASHBOARD_PID" ]; then
    echo -e "   ${YELLOW}⚡${NC} Already running (PID: $DASHBOARD_PID)"
    echo "$DASHBOARD_PID" >> "$PIDS_FILE"
else
    streamlit run local_dashboard.py --server.port 8501 --server.headless true > logs/dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    echo "$DASHBOARD_PID" >> "$PIDS_FILE"
    sleep 3
    
    if ps -p $DASHBOARD_PID > /dev/null; then
        echo -e "   ${GREEN}✓${NC} Dashboard started (PID: $DASHBOARD_PID)"
    else
        echo -e "   ${YELLOW}⚠${NC} Failed to start Dashboard"
    fi
fi
echo "   📊 http://localhost:8501"
echo ""

# ============================================================================
# STEP 3: Run Daily Scanner (if market hours)
# ============================================================================
echo -e "${BLUE}[3/5]${NC} Running Daily Scanner..."

# Check if it's market hours (9:30 AM - 4:00 PM ET)
current_hour=$(date +%H)
current_min=$(date +%M)
current_time=$((10#$current_hour * 60 + 10#$current_min))
market_open=$((9 * 60 + 30))  # 9:30 AM
market_close=$((16 * 60))      # 4:00 PM

if [ $current_time -ge $market_open ] && [ $current_time -le $market_close ]; then
    echo "   Market is OPEN - Running scanner..."
    python daily_scanner.py --mode scan --export scan_results.json 2>&1 | tee logs/scanner_$(date +%Y%m%d_%H%M%S).log
    
    if [ -f "scan_results.json" ]; then
        echo -e "   ${GREEN}✓${NC} Scanner completed successfully"
        echo "   📄 Results: scan_results.json"
    else
        echo -e "   ${YELLOW}⚠${NC} Scanner ran but no results file"
    fi
else
    echo -e "   ${YELLOW}⏸${NC}  Market is CLOSED - Skipping scanner"
    echo "   Using existing scan_results.json if available"
fi
echo ""

# ============================================================================
# STEP 4: Run Portfolio Manager with Profit Taker
# ============================================================================
echo -e "${BLUE}[4/5]${NC} Executing Portfolio Manager..."

# Ask user for mode
echo -n "   Run in [L]ive or [D]ry-run mode? (default: dry-run): "
read -t 10 mode_choice || mode_choice="d"

case ${mode_choice,,} in
    l|live)
        MODE="live"
        echo -e "   ${YELLOW}⚡${NC} LIVE MODE - Real orders will be placed!"
        ;;
    *)
        MODE="dry-run"
        echo -e "   ${GREEN}🔍${NC} DRY-RUN MODE - No real orders"
        ;;
esac

# Verify scanner results exist
if [ ! -f "scan_results.json" ]; then
    echo -e "   ${RED}✗${NC} ERROR: scan_results.json not found!"
    echo "   Run: python daily_scanner.py --export scan_results.json"
    exit 1
fi
echo -e "   ${GREEN}✓${NC} Scanner results found"

# Ask about profit taker (only if live mode)
if [ "$MODE" == "live" ]; then
    echo -n "   Start profit taker? [Y/n]: "
    read -t 10 pt_choice || pt_choice="y"
    
    case ${pt_choice,,} in
        n|no)
            START_PT=""
            ;;
        *)
            echo -n "   Profit taker mode [c]onservative/[m]oderate/[a]ggressive (default: moderate): "
            read -t 10 pt_mode || pt_mode="m"
            
            case ${pt_mode,,} in
                c|conservative)
                    PT_MODE="conservative"
                    ;;
                a|aggressive)
                    PT_MODE="aggressive"
                    ;;
                *)
                    PT_MODE="moderate"
                    ;;
            esac
            
            START_PT="--start-profit-taker --profit-taker-mode $PT_MODE"
            ;;
    esac
else
    START_PT=""
fi

echo ""
echo "   Executing: python trading_automation.py --mode $MODE $START_PT"
echo ""

python trading_automation.py --mode $MODE $START_PT 2>&1 | tee logs/pm_execution_$(date +%Y%m%d_%H%M%S).log

if [ $? -eq 0 ]; then
    echo -e "   ${GREEN}✓${NC} Portfolio Manager execution completed"
else
    echo -e "   ${RED}✗${NC} Portfolio Manager encountered errors"
fi
echo ""

# ============================================================================
# STEP 5: Start Cloud Sync (Optional)
# ============================================================================
echo -e "${BLUE}[5/5]${NC} Cloud Sync..."
echo -n "   Start cloud sync? [y/N]: "
read -t 10 sync_choice || sync_choice="n"

case ${sync_choice,,} in
    y|yes)
        echo "   Starting cloud sync in watch mode..."
        ./sync_to_cloud.sh --watch > logs/cloud_sync.log 2>&1 &
        SYNC_PID=$!
        echo "$SYNC_PID" >> "$PIDS_FILE"
        sleep 2
        
        if ps -p $SYNC_PID > /dev/null; then
            echo -e "   ${GREEN}✓${NC} Cloud sync started (PID: $SYNC_PID)"
        else
            echo -e "   ${YELLOW}⚠${NC} Cloud sync failed to start"
        fi
        ;;
    *)
        echo -e "   ${YELLOW}⏸${NC}  Skipping cloud sync"
        ;;
esac
echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ TRADING SYSTEM STARTED${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 RUNNING SERVICES:"

# Check WebSocket Server
if ps -p $BROADCAST_PID > /dev/null 2>&1; then
    echo -e "   ${GREEN}●${NC} WebSocket Server (PID: $BROADCAST_PID) - ws://localhost:8765"
else
    echo -e "   ${RED}●${NC} WebSocket Server - STOPPED"
fi

# Check Dashboard
if ps -p $DASHBOARD_PID > /dev/null 2>&1; then
    echo -e "   ${GREEN}●${NC} Local Dashboard (PID: $DASHBOARD_PID) - http://localhost:8501"
else
    echo -e "   ${RED}●${NC} Local Dashboard - STOPPED"
fi

# Check for profit taker process
PT_PID=$(pgrep -f "intraday_profit_taker.py" | head -1)
if [ -n "$PT_PID" ]; then
    echo -e "   ${GREEN}●${NC} Profit Taker (PID: $PT_PID) - Monitoring positions"
    echo "$PT_PID" >> "$PIDS_FILE"
fi

# Check cloud sync
if [ -n "$SYNC_PID" ] && ps -p $SYNC_PID > /dev/null 2>&1; then
    echo -e "   ${GREEN}●${NC} Cloud Sync (PID: $SYNC_PID) - Syncing every 60s"
fi

echo ""
echo "📊 MONITORING:"
echo "   Dashboard: http://localhost:8501"
echo "   Logs: ./logs/"
echo ""
echo "🛑 TO STOP ALL SERVICES:"
echo "   ./stop_trading_systems.sh"
echo ""
echo "📝 SAVED PIDS TO: $PIDS_FILE"
echo ""

# Offer to open dashboard
echo -n "Open dashboard in browser? [Y/n]: "
read -t 10 open_choice || open_choice="y"

case ${open_choice,,} in
    n|no)
        ;;
    *)
        echo "   Opening http://localhost:8501..."
        if command -v open > /dev/null; then
            open http://localhost:8501
        elif command -v xdg-open > /dev/null; then
            xdg-open http://localhost:8501
        fi
        ;;
esac

echo ""
echo "✨ System is ready! Press Ctrl+C to exit (services will continue running)"
echo ""
