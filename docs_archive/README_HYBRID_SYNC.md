# Hybrid Local + Cloud Sync System

## Overview

Your trading system now has **dual-logging**:

1. **Local WebSocket** - Real-time events on your machine (`ws://localhost:8765`)
2. **Public JSON** - Sanitized events synced to GitHub → Streamlit Cloud

## How It Works

```
Trading Scripts (local)
   ↓
   ├─→ WebSocket Server (ws://localhost:8765) ──→ Local Viewer (real-time)
   └─→ public_events.json (sanitized) ──→ GitHub ──→ Cloud Viewer (delayed)
```

### Data Sanitization

Sensitive data is automatically removed from `public_events.json`:

| Original | Sanitized |
|----------|-----------|
| `$125,432.50` | `$100K+` |
| `BUY 150 NVDA` | `BUY XX NVDA` |
| `+$3,247.80` | `+$1K-10K` |
| `quantity: 150` | *(removed)* |
| `nav: 125432.50` | *(removed)* |
| `order_id: abc123` | *(removed)* |

**What stays:**
- Event types (scan, strategy, order, profit)
- Tickers (NVDA, TSLA, etc.)
- Percentages (gain +6.3%)
- Timestamps
- Decision rationale

## Usage at Market Open

### Step 1: Start Local Systems (9:25 AM)

```bash
cd trading-system
./start_trading_systems.sh
```

This starts:
- WebSocket server (localhost:8765)
- Dashboard viewer (localhost:8501)

### Step 2: Run Trading Scripts (9:30 AM)

```bash
# Scanner
python daily_scanner.py --mode scan --export scan_results.json

# Trading automation  
python trading_automation.py --mode live

# Profit taker
python intraday_profit_taker.py --mode aggressive
```

**Events are now dual-logged:**
- ✅ Real-time to WebSocket → Local viewer (instant)
- ✅ Sanitized to `public_events.json` → Cloud viewer (after sync)

### Step 3: Auto-Sync to Cloud (Background)

**Option A: Manual sync** (after each script run)
```bash
./sync_to_cloud.sh
```

**Option B: Auto-sync** (continuous, every 60 seconds)
```bash
./sync_to_cloud.sh --watch
```

This runs in background and syncs whenever `public_events.json` or `scan_results.json` change.

**Option C: Custom interval**
```bash
./sync_to_cloud.sh --watch --interval 30  # Sync every 30 seconds
```

### Complete Workflow

```bash
# Terminal 1: Start systems
./start_trading_systems.sh

# Terminal 2: Auto-sync (keeps running)
./sync_to_cloud.sh --watch

# Terminal 3: Scanner
python daily_scanner.py --mode scan --export scan_results.json

# Terminal 4: Trading automation
python trading_automation.py --mode live

# Terminal 5: Profit taker
python intraday_profit_taker.py --mode aggressive
```

Now:
- **Local viewer** (localhost:8501) shows real-time events via WebSocket
- **Cloud viewer** (streamlit.app) shows sanitized events via GitHub sync
- Auto-sync pushes updates every 60 seconds

## What You'll See

### Local Viewer (Real-Time)
```
9:30:02 🔍 [Market Scanner] Daily Market Scan Started
9:30:15 🎯 [Market Scanner] Scoring complete - Top 5: RKLB (89), AA (87)...
9:30:18 🟢 [Market Scanner] Market Regime: RISK_ON
9:30:25 🎯 [Trading Automation] Selected CORE strategy | NAV: $127,432.50
9:30:27 📊 [Trading Automation] SELL 150 MSFT (MARKET)
9:30:28 📊 [Trading Automation] BUY 200 RKLB (MARKET)
10:15:43 💰 [Profit Taker] PROFIT TAKEN: TSLA +6.3% ($3,247.80)
```

### Cloud Viewer (Sanitized, Delayed)
```
9:31:00 🔍 [Market Scanner] Daily Market Scan Started
9:31:15 🎯 [Market Scanner] Scoring complete - Top 5: RKLB (89), AA (87)...
9:31:18 🟢 [Market Scanner] Market Regime: RISK_ON
9:31:25 🎯 [Trading Automation] Selected CORE strategy | NAV: $100K+
9:31:27 📊 [Trading Automation] SELL XX MSFT (MARKET)
9:31:28 📊 [Trading Automation] BUY XX RKLB (MARKET)
10:16:00 💰 [Profit Taker] PROFIT TAKEN: TSLA +6.3% ($1K-10K)
```

## Files Created

- `public_event_exporter.py` - Sanitization engine
- `public_events.json` - Public event log (synced to GitHub)

## Files Modified

- `event_broadcaster.py` - Now dual-logs to WebSocket + JSON
- `trading_dashboard_viewer.py` - Reads from public_events.json
- `sync_to_cloud.sh` - Enhanced with --watch mode
- `.gitignore` - Allows public_events.json

## Testing

### Test 1: Verify Sanitization

```bash
python public_event_exporter.py
cat public_events.json
```

You should see sanitized dollar amounts and no quantities.

### Test 2: Test Dual-Logging

```bash
# Terminal 1: Start WebSocket server
python log_broadcast_server.py

# Terminal 2: Run test
python test_broadcasting.py

# Check both outputs:
# 1. WebSocket server logs show events received
# 2. public_events.json contains sanitized events
cat public_events.json | python -m json.tool | tail -20
```

### Test 3: Test Auto-Sync

```bash
# Terminal 1: Start auto-sync
./sync_to_cloud.sh --watch

# Terminal 2: Generate events
python test_broadcasting.py

# Wait 60 seconds, should see:
# "📤 Syncing public data to GitHub..."
# "✅ Synced at 10:23:45"
```

## Streamlit Cloud Setup

On Streamlit Cloud dashboard:

1. Repository is already connected
2. Branch: `main`
3. Main file: `trading_dashboard_viewer.py`

When you push `public_events.json`:
- GitHub webhook triggers
- Streamlit Cloud auto-redeploys
- New events appear in PM Activity Feed

## Sync Frequency Recommendations

### Conservative (Free GitHub tier)
```bash
./sync_to_cloud.sh --watch --interval 300  # Every 5 minutes
```

### Moderate
```bash
./sync_to_cloud.sh --watch --interval 60   # Every minute (default)
```

### Aggressive (Pro users)
```bash
./sync_to_cloud.sh --watch --interval 30   # Every 30 seconds
```

## Monitoring

### Check Sync Status
```bash
# See when last synced
git log --oneline -5

# See what changed
git diff public_events.json scan_results.json
```

### Check Event Count
```bash
cat public_events.json | jq '.event_count'
cat public_events.json | jq '.last_updated'
```

### View Latest Events
```bash
cat public_events.json | jq '.events[-5:]'  # Last 5 events
```

## Troubleshooting

### "No events in cloud viewer"
- Check `public_events.json` exists locally
- Verify auto-sync is running (`ps aux | grep sync_to_cloud`)
- Check GitHub for recent commits
- Wait for Streamlit Cloud redeploy (~2 min)

### "Events not sanitized"
- Verify `public_event_exporter.py` is imported
- Check `event_broadcaster.py` has public exporter enabled
- Test with `python public_event_exporter.py`

### "Sync failing"
- Check GitHub credentials: `git push origin main`
- Verify files are tracked: `git status`
- Check `.gitignore` allows `public_events.json`

## Benefits

✅ **Security**: Sensitive data never leaves your machine  
✅ **Transparency**: Public can see decision-making process  
✅ **Real-time local**: Zero-latency monitoring on your machine  
✅ **Cloud accessible**: Share portfolio performance publicly  
✅ **Automatic**: Set it and forget it with --watch mode  
✅ **Compliant**: No API keys, account numbers, or exact positions exposed  

## Next Steps

1. **Test locally**: Run complete workflow with auto-sync
2. **Deploy to cloud**: Push to GitHub, verify Streamlit updates
3. **Monitor market open**: Watch events flow local → cloud
4. **Share link**: Give Streamlit Cloud URL to viewers
5. **Optimize interval**: Adjust sync frequency based on GitHub rate limits

---

**You now have the best of both worlds:**
- Private, real-time local monitoring
- Public, sanitized cloud sharing
- Automatic synchronization
- Complete control over what's shared

🚀 **Ready for market open!**
