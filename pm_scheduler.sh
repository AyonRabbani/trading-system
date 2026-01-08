#!/bin/bash

# Portfolio Manager Scheduler
# Runs PM 4 times per day during market hours (9:30 AM - 4:00 PM ET)
# Schedule: 10:00 AM, 12:00 PM, 2:00 PM, 3:30 PM ET

set -e

cd "$(dirname "$0")"

# Configuration
LOG_FILE="logs/pm_scheduler.log"
LOCK_FILE="/tmp/pm_scheduler.lock"
TIMEZONE="America/New_York"

# Market hours (ET)
MARKET_OPEN_HOUR=9
MARKET_OPEN_MIN=30
MARKET_CLOSE_HOUR=16
MARKET_CLOSE_MIN=0

# PM run times (ET) - evenly spaced during market hours
PM_TIMES=(
    "10:00"  # 30 min after open
    "12:00"  # Midday
    "14:00"  # 2:00 PM
    "15:30"  # 30 min before close
)

# Create logs directory
mkdir -p logs

# Logging function
log() {
    echo "[$(TZ=$TIMEZONE date '+%Y-%m-%d %H:%M:%S %Z')] $1" | tee -a "$LOG_FILE"
}

# Check if market is open
is_market_open() {
    local current_day=$(TZ=$TIMEZONE date +%u)  # 1=Monday, 7=Sunday
    local current_hour=$(TZ=$TIMEZONE date +%H)
    local current_min=$(TZ=$TIMEZONE date +%M)
    
    # Skip weekends (6=Saturday, 7=Sunday)
    if [ "$current_day" -ge 6 ]; then
        return 1
    fi
    
    # Check if within market hours (9:30 AM - 4:00 PM ET)
    local current_time=$((current_hour * 60 + current_min))
    local open_time=$((MARKET_OPEN_HOUR * 60 + MARKET_OPEN_MIN))
    local close_time=$((MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MIN))
    
    if [ "$current_time" -ge "$open_time" ] && [ "$current_time" -lt "$close_time" ]; then
        return 0
    fi
    
    return 1
}

# Check if it's time to run PM
should_run_pm() {
    local current_time=$(TZ=$TIMEZONE date +%H:%M)
    
    for scheduled_time in "${PM_TIMES[@]}"; do
        if [ "$current_time" == "$scheduled_time" ]; then
            return 0
        fi
    done
    
    return 1
}

# Check for existing lock
if [ -f "$LOCK_FILE" ]; then
    LOCK_PID=$(cat "$LOCK_FILE")
    if ps -p "$LOCK_PID" > /dev/null 2>&1; then
        log "⚠️  PM already running (PID: $LOCK_PID), skipping this run"
        exit 0
    else
        log "Removing stale lock file"
        rm -f "$LOCK_FILE"
    fi
fi

# Create lock file
echo $$ > "$LOCK_FILE"

# Cleanup function
cleanup() {
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

# Main scheduler loop
log "========================================================================"
log "Portfolio Manager Scheduler Started"
log "========================================================================"
log "Schedule: ${PM_TIMES[*]} ET"
log "Market Hours: ${MARKET_OPEN_HOUR}:$(printf '%02d' $MARKET_OPEN_MIN) - ${MARKET_CLOSE_HOUR}:$(printf '%02d' $MARKET_CLOSE_MIN) ET"
log "Timezone: $TIMEZONE"
log ""

while true; do
    # Check if market is open
    if ! is_market_open; then
        NEXT_OPEN=$(TZ=$TIMEZONE date -v +1d -v ${MARKET_OPEN_HOUR}H -v ${MARKET_OPEN_MIN}M -v 0S '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "next trading day")
        log "Market closed. Next check at $NEXT_OPEN"
        sleep 900  # Check every 15 minutes when market closed
        continue
    fi
    
    # Check if it's time to run PM
    if should_run_pm; then
        log ""
        log "========================================================================"
        log "🚀 Triggering Portfolio Manager Run"
        log "========================================================================"
        log "Time: $(TZ=$TIMEZONE date '+%H:%M:%S %Z')"
        log ""
        
        # Run scanner first
        log "Step 1/2: Running scanner..."
        if python daily_scanner.py --export scan_results.json >> "$LOG_FILE" 2>&1; then
            log "✅ Scanner complete"
        else
            log "❌ Scanner failed - skipping PM run"
            sleep 60  # Wait a minute before next check
            continue
        fi
        
        # Run Portfolio Manager
        log ""
        log "Step 2/2: Running Portfolio Manager..."
        if python trading_automation.py --mode live >> "$LOG_FILE" 2>&1; then
            log "✅ Portfolio Manager complete"
            log ""
            log "📊 Summary:"
            
            # Show PM state
            if [ -f "pm_state.json" ]; then
                python -c "
import json
try:
    with open('pm_state.json') as f:
        state = json.load(f)
        print(f\"   Last Strategy: {state.get('last_strategy', 'N/A')}\")
        print(f\"   Last Run: {state.get('last_run', 'N/A')}\")
        if 'cooldown_until' in state and state['cooldown_until']:
            print(f\"   Cooldown Until: {state['cooldown_until']}\")
except Exception as e:
    print(f'   Could not read state: {e}')
" | tee -a "$LOG_FILE"
            fi
            
            log ""
            log "Next PM run at: ${PM_TIMES[*]} ET"
        else
            log "❌ Portfolio Manager failed"
        fi
        
        log "========================================================================"
        log ""
        
        # Sleep for 61 seconds to avoid running again in same minute
        sleep 61
    else
        # Not a scheduled time, check again in 30 seconds
        sleep 30
    fi
done
