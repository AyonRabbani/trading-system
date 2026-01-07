#!/bin/bash
# Sync trading activity to GitHub for Streamlit Cloud deployment
# Run this after scanner completes to update cloud deployment

cd "$(dirname "$0")"

echo "🔄 Syncing trading data to GitHub..."

# Add scan results (force-add since *.json is gitignored but scan_results.json is excepted)
if [ -f "scan_results.json" ]; then
  git add -f scan_results.json
  echo "✅ Added scan_results.json"
fi

# Check if there are changes to commit
if [[ `git status --porcelain` ]]; then
  git commit -m "Auto-sync: Update scanner results $(date '+%Y-%m-%d %H:%M:%S')"
  git push origin main
  echo "✅ Synced to GitHub - Streamlit Cloud will auto-redeploy"
else
  echo "ℹ️  No changes to sync"
fi
