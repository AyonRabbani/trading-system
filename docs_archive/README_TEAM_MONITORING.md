# Team Monitoring Setup

This system automatically shares full trading data with your friends and team via GitHub.

## 🔄 How It Works

1. **Local Dashboard** runs and broadcasts all events via WebSocket
2. **Broadcast Server** exports ALL events to `public_events.json` (NO sanitization)
3. **Cloud Sync** automatically pushes to GitHub every 30 seconds
4. **Public Dashboard** on Streamlit Cloud reads from GitHub and displays live data
5. **Team** can view real-time activity at your public dashboard URL

## 📊 Data Shared (Full Visibility)

- **Account Value**: Exact dollar amounts
- **Positions**: Ticker, quantity, entry price, current value
- **Orders**: BUY/SELL with exact quantities and prices
- **Profit/Loss**: Real dollar amounts and percentages
- **Strategy Performance**: All backtest results and returns
- **Scanner Results**: Full ticker recommendations with scores

**NO DATA IS HIDDEN** - Your team sees everything you see locally.

## 🚀 Quick Start

### 1. Start Full System (Auto-Sync Enabled)
```bash
./start_full_trading_system.sh
```
This automatically starts:
- WebSocket Broadcast Server
- Local Dashboard
- Daily Scanner
- Portfolio Manager
- Profit Taker
- **Cloud Sync (auto-enabled, syncs every 30 seconds)**

### 2. Team Access

Share your public dashboard URL with your team:
- If using Streamlit Cloud: `https://your-app.streamlit.app`
- If self-hosted: Configure and share URL

They'll see:
- Live account status
- Current positions
- Recent orders
- Scanner recommendations
- Strategy performance
- All events and activity

## 📁 Files Synced to GitHub

- `public_events.json` - All trading events (last 200)
- `scan_results.json` - Latest scanner results with recommendations
- Auto-committed every 30 seconds when data changes

## 🛠️ Manual Control

### Check Sync Status
```bash
# View sync logs
tail -f logs/cloud_sync.log

# Check running processes
ps aux | grep sync_to_cloud
```

### Stop/Start Sync
```bash
# Stop
./stop_trading_systems.sh

# Start just sync (if needed separately)
./sync_to_cloud.sh --watch --interval 30
```

### Adjust Sync Frequency
Edit `start_full_trading_system.sh` line 186:
```bash
./sync_to_cloud.sh --watch --interval 30  # Change 30 to desired seconds
```

## 🔐 Security Notes

- This shares FULL trading data with anyone who has your dashboard URL
- Only share URL with trusted team members and friends
- GitHub repo should be private if it contains API keys
- `public_events.json` and `scan_results.json` are force-added (not gitignored)
- All other files with sensitive data (.env, keys, etc.) remain gitignored

## 📱 Team Monitoring Features

Your team can see on the public dashboard:

### Real-Time Updates
- Orders placed (exact quantities and prices)
- Positions entered/exited
- Profit targets hit
- Stop losses triggered
- Account balance changes

### Strategy Insights
- Which strategy is active (BUY_HOLD, TACTICAL, SPEC, ASYM)
- Backtest performance for all strategies
- Why Portfolio Manager selected current strategy
- Risk management actions (liquidations, cooldowns)

### Scanner Results
- Top scoring tickers
- Rotation recommendations
- Market regime (RISK_ON/RISK_OFF)
- Hot/cold sectors
- Score improvements for recommended trades

## 🎯 Use Cases

- **Live Monitoring**: Team watches trades execute in real-time
- **Performance Tracking**: Friends see your returns and strategy
- **Learning**: Team studies your decision-making process
- **Collaboration**: Discuss trades and strategies as they happen
- **Transparency**: Full visibility builds trust

## 🔄 Update Cycle

```
Trading Event
    ↓
WebSocket Broadcast (instant)
    ↓
local_dashboard.py (instant display)
    ↓
public_events.json (instant export)
    ↓
sync_to_cloud.sh (30 sec polling)
    ↓
Git Push to GitHub (when changes detected)
    ↓
Streamlit Cloud Auto-Redeploy (~1 min)
    ↓
Team Sees Update on Public Dashboard
```

**Total delay: ~90 seconds from event to team visibility**

## 🐛 Troubleshooting

### Sync Not Working
```bash
# Check if sync is running
ps aux | grep sync_to_cloud

# View sync errors
cat logs/cloud_sync.log

# Test manual sync
./sync_to_cloud.sh
```

### Team Not Seeing Updates
1. Check Streamlit Cloud deployment status
2. Verify GitHub commits are going through
3. Ensure public_events.json is in repo
4. Check dashboard is reading from correct repo URL

### Missing Events
1. Verify WebSocket server is running: `ps aux | grep log_broadcast_server`
2. Check broadcast server logs: `tail -f logs/broadcast_server.log`
3. Ensure scripts are connecting to WebSocket (check for "Connected to broadcast server" in logs)

## 📞 Support

If team monitoring isn't working:
1. Check all services are running: `cat .trading_pids`
2. Verify sync is active: `tail -f logs/cloud_sync.log`
3. Test GitHub access: `git push` manually
4. Check public_events.json exists and has recent timestamp
