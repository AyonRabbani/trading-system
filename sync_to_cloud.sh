#!/bin/bash
# Sync trading activity to GitHub for Streamlit Cloud deployment
# Enhanced with auto-sync mode for continuous updates during market hours
# Run this after scanner completes to update cloud deployment
# Or use --watch mode for automatic syncing every 60 seconds

cd "$(dirname "$0")"

AUTO_SYNC=false
INTERVAL=60

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --watch)
            AUTO_SYNC=true
            shift
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

sync_once() {
    # Check if there are changes to public files
    if git diff --quiet public_events.json scan_results.json dashboard_state.json 2>/dev/null; then
        return 0
    fi
    
    echo "📤 Syncing public data to GitHub..."
    
    # Add public files (force-add since *.json is gitignored but these are excepted)
    git add -f public_events.json scan_results.json dashboard_state.json 2>/dev/null
    
    if [[ `git status --porcelain` ]]; then
        # Commit with timestamp
        git commit -m "Auto-sync: Update public data $(date '+%Y-%m-%d %H:%M:%S')" --quiet
        
        # Push to GitHub
        if git push origin main --quiet 2>&1; then
            echo "✅ Synced at $(date '+%H:%M:%S') - Streamlit Cloud will auto-redeploy"
            return 0
        else
            echo "⚠️  Push failed - will retry next cycle"
            return 1
        fi
    else
        return 0
    fi
}

if [ "$AUTO_SYNC" = true ]; then
    echo "🔄 Auto-sync enabled - watching for changes every ${INTERVAL} seconds"
    echo "   Files monitored: public_events.json, scan_results.json, dashboard_state.json"
    echo "   Press Ctrl+C to stop"
    echo ""
    
    # Initial sync
    sync_once
    
    # Watch loop
    while true; do
        sleep "$INTERVAL"
        sync_once
    done
else
    # Single sync
    sync_once
fi
