# Syncing Local Trading System to Streamlit Cloud

This guide explains how to keep your Streamlit Cloud deployment updated with local trading activity.

## Architecture

### Local System (Your Machine)
- **Runs**: Scanner, Trading Automation, Profit Taker
- **Generates**: Log files, scan_results.json
- **Uploads**: Activity data to GitHub

### Cloud System (Streamlit Cloud)
- **Reads**: Portfolio data from Alpaca API (real-time)
- **Reads**: scan_results.json from GitHub repo
- **Displays**: Portfolio + Scanner insights (works now)
- **Missing**: Log files for PM activity feed

## Option 1: Automated GitHub Sync (Recommended)

### Step 1: Create Sync Script

Create `sync_to_cloud.sh` in your trading-system folder:

```bash
#!/bin/bash
# Sync trading activity to GitHub for cloud deployment

cd "$(dirname "$0")"

# Add scan results
git add scan_results.json

# Commit if changes exist
if [[ `git status --porcelain` ]]; then
  git commit -m "Auto-sync: Update scanner results $(date '+%Y-%m-%d %H:%M')"
  git push origin main
  echo "✅ Synced to GitHub"
else
  echo "ℹ️  No changes to sync"
fi
```

Make it executable:
```bash
chmod +x sync_to_cloud.sh
```

### Step 2: Automate with Cron

Add to your crontab (`crontab -e`):

```bash
# Sync scanner results every hour
0 * * * * cd /Users/ayon/Desktop/The\ Great\ Lock\ In/Research/trading-system && ./sync_to_cloud.sh >> sync.log 2>&1

# Run scanner daily at 4 PM EST (after market close)
0 16 * * 1-5 cd /Users/ayon/Desktop/The\ Great\ Lock\ In/Research/trading-system && python daily_scanner.py --mode scan --export scan_results.json && ./sync_to_cloud.sh
```

## Option 2: Manual Sync

After running scanner locally:

```bash
cd trading-system
git add scan_results.json
git commit -m "Update scanner results"
git push origin main
```

Streamlit Cloud will auto-redeploy with new data!

## Option 3: Cloud Storage for Logs (Advanced)

For real-time log syncing, use S3/GCS:

### Setup AWS S3

1. **Create S3 Bucket**: `trading-system-logs`

2. **Update scripts to upload logs**:

```python
import boto3
from datetime import datetime

s3 = boto3.client('s3')

def upload_log_to_s3(log_file):
    bucket = 'trading-system-logs'
    key = f"logs/{datetime.now().strftime('%Y/%m/%d')}/{log_file}"
    s3.upload_file(log_file, bucket, key)
```

3. **Update viewer to read from S3**:

```python
def get_latest_log_from_s3(prefix):
    s3 = boto3.client('s3')
    response = s3.list_objects_v2(
        Bucket='trading-system-logs',
        Prefix=prefix
    )
    # Download and parse latest log
```

4. **Add AWS credentials to Streamlit secrets**:

```toml
AWS_ACCESS_KEY_ID = "your_key"
AWS_SECRET_ACCESS_KEY = "your_secret"
AWS_REGION = "us-east-1"
```

## What Works Now (Without Log Sync)

✅ **Real-time portfolio data** (from Alpaca API)
✅ **Current positions and P&L** 
✅ **30-day performance charts**
✅ **Scanner recommendations** (if scan_results.json is synced)
✅ **Recent order history**

## What Requires Sync

⏳ **PM Activity Feed** - needs log files
⏳ **Strategy decision timeline** - needs trading logs
⏳ **Profit-taking events** - needs profit_taker logs

## Recommended Setup

**For Public Viewers (Streamlit Cloud):**
- Deploy viewer showing portfolio + scanner insights
- Sync scan_results.json daily
- Activity feed shows "run locally for full details"

**For Personal Use (Local):**
- Run full dashboard with all controls
- See complete PM activity feed
- Execute trading operations

## Quick Start

1. **Test viewer locally with logs**:
```bash
# Run scanner
python daily_scanner.py --mode scan

# Start viewer
streamlit run trading_dashboard_viewer.py

# You should see PM Activity Feed populated!
```

2. **Deploy to Streamlit Cloud**:
- Portfolio data works immediately (Alpaca API)
- Scanner insights work if you sync scan_results.json
- Activity feed will be empty (run locally to see)

3. **Setup auto-sync** (optional):
```bash
./sync_to_cloud.sh
```

## Summary

**Current State**: 
- Viewer reads real-time portfolio from Alpaca ✅
- Viewer reads scanner results from file ✅
- Viewer reads logs from local filesystem ⏳

**For Cloud PM Activity Feed**, you need ONE of:
1. Sync logs to GitHub (simple but manual)
2. Use cloud storage like S3 (real-time but complex)
3. Run viewer locally (immediate but not public)

**Recommendation**: Keep viewer on Streamlit Cloud for portfolio monitoring, and note that "full PM activity feed available when running locally". This is common for trading systems - public view shows results, internal view shows decisions.

