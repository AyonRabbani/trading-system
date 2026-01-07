# Live Event Monitoring Setup

This guide shows how to set up real-time monitoring of all trading system activities at market open.

## Architecture

```
┌─────────────────────┐
│  Daily Scanner      │────┐
│  (daily_scanner.py) │    │
└─────────────────────┘    │
                           │
┌─────────────────────┐    │    ┌──────────────────────┐     ┌─────────────────────┐
│  Trading Automation │────┼───▶│  WebSocket Server    │────▶│  Dashboard Viewer   │
│ (trading_auto.py)   │    │    │ (log_broadcast...py) │     │ (viewer.py)         │
└─────────────────────┘    │    └──────────────────────┘     └─────────────────────┘
                           │           ws://localhost:8765
┌─────────────────────┐    │
│  Profit Taker       │────┘
│  (profit_taker.py)  │
└─────────────────────┘
```

## Quick Start at Market Open

### Step 1: Start the WebSocket Server

This broadcasts events from all trading scripts to connected viewers.

```bash
cd /Users/ayon/Desktop/The\ Great\ Lock\ In/Research/trading-system
python log_broadcast_server.py
```

You should see:
```
✓ Server listening on ws://localhost:8765
Waiting for connections from trading scripts and viewers...
```

### Step 2: Start the Dashboard Viewer

Open a new terminal:

```bash
streamlit run trading_dashboard_viewer.py
```

The viewer will:
- Connect to the WebSocket server
- Show real-time events in the PM Activity Feed
- Display portfolio data from Alpaca API
- Show latest scanner results from scan_results.json

### Step 3: Start Trading Scripts

Now start any or all of the trading scripts. Each will automatically broadcast events.

#### Run Daily Scanner (once at market open):
```bash
python daily_scanner.py --mode scan --export scan_results.json
```

Events broadcasted:
- 🔍 Scan started
- 📊 Loading universe data
- 🎯 Scoring complete with top 5
- 🟢/🔴 Market regime detection
- 🔄 Rotation recommendations

#### Run Trading Automation (once at market open):
```bash
python trading_automation.py --mode live
```

Events broadcasted:
- 🎯 Strategy selection (CORE/SPECULATIVE/ASYMMETRIC/TACTICAL)
- 📊 Order placements (BUY/SELL with quantities)
- ⚖️ Rebalancing completion

#### Run Profit Taker (continuous during market hours):
```bash
python intraday_profit_taker.py --mode aggressive
```

Events broadcasted:
- 💰 Profit-taking actions with gain %
- Entry/exit prices
- Hold duration
- Profit dollars

## What You'll See

### In the Dashboard Viewer

1. **Tab 1: PM Activity Feed** (NEW - Real-time events!)
   - Live event stream with icons
   - Timeline chart showing event distribution
   - PM Decision Summary with latest strategy
   - System Status indicators (🟢 Active / ⚪ Inactive)
   
2. **Tab 2: Portfolio Overview**
   - Real-time portfolio value from Alpaca API
   - 30-day performance chart
   - Performance metrics (Sharpe, drawdown, volatility)

3. **Tab 3: Positions**
   - Current holdings with P&L
   - Position charts
   - Position statistics

4. **Tab 4: Market Analysis**
   - Latest scanner results
   - Market regime
   - Top scorers
   - Rotation recommendations

5. **Tab 5: Recent Orders**
   - Order history from Alpaca API
   - Filterable by status

### Event Types

- 🔍 **scan** - Scanner analysis events
- 🎯 **strategy** - Strategy selection decisions
- 📊 **order** - Buy/sell order executions
- 💰 **profit** - Profit-taking actions
- ⚖️ **rebalance** - Portfolio rebalancing
- ℹ️ **info** - Informational messages
- ⚠️ **warning** - Warnings
- ❌ **error** - Error conditions

## Complete Market Open Workflow

### 9:25 AM ET - Pre-Market Setup
```bash
# Terminal 1: Start broadcast server
python log_broadcast_server.py

# Terminal 2: Start dashboard viewer
streamlit run trading_dashboard_viewer.py
```

### 9:30 AM ET - Market Open
```bash
# Terminal 3: Run scanner
python daily_scanner.py --mode scan --export scan_results.json

# Wait for scanner to complete (~20 seconds)
# Then sync to cloud (if using Streamlit Cloud deployment)
./sync_to_cloud.sh

# Terminal 4: Run trading automation
python trading_automation.py --mode live

# Terminal 5: Start profit taker (runs until market close)
python intraday_profit_taker.py --mode aggressive
```

### 9:31 AM - Watch Live Events

The dashboard viewer will show:
1. Scanner completes, broadcasts top opportunities
2. Trading automation selects strategy, broadcasts decision
3. Orders are placed, each broadcasted individually
4. Profit taker monitors positions in real-time
5. Any profit-taking triggers broadcast with details

### 4:00 PM ET - Market Close

Profit taker automatically stops monitoring at market close.
You can stop all scripts with Ctrl+C.

## Advanced Features

### Auto-Refresh
Enable auto-refresh in the sidebar for 30-second updates of:
- Portfolio data
- Live events
- System status

### Event Filtering
Filter events by type in the sidebar:
- Show only strategy decisions
- Show only order executions
- Show only profit-taking events

### Multiple Viewers
You can connect multiple viewers to the same WebSocket server.
Each will receive all events in real-time.

### Cloud Deployment Note

The WebSocket server and live events only work when running **locally**.

On Streamlit Cloud:
- Portfolio data works (via Alpaca API)
- Scanner results work (via GitHub sync)
- PM Activity Feed shows explanatory message
- Historical logs work (if uploaded manually)

For full PM transparency on Streamlit Cloud, you would need:
- Cloud-hosted WebSocket server (e.g., on Heroku/Railway)
- Update broadcast server URL in scripts
- Or use cloud storage (S3) for log syncing

## Troubleshooting

### "Could not connect to broadcast server"
- Ensure `log_broadcast_server.py` is running
- Check that port 8765 is not blocked
- Server must start before trading scripts

### "No events showing"
- Verify trading scripts are running
- Check that scripts include broadcaster import
- Look for connection messages in server terminal

### "Connection closed"
- Normal when refreshing the viewer
- Viewer automatically reconnects
- Event history is preserved on server

### Scripts not broadcasting
- Ensure `event_broadcaster.py` is in the same directory
- Check that `get_broadcaster()` is called in script
- Verify `broadcaster.broadcast_event()` calls are present

## Performance Notes

- WebSocket server is lightweight (~1-2% CPU)
- Can handle 100+ events per second
- Stores last 100 events for new viewers
- No database required
- Zero-latency event delivery

## Security Notes

For production deployment:
- Add authentication to WebSocket server
- Use wss:// (secure WebSocket) instead of ws://
- Firewall port 8765 to local network only
- Consider using nginx proxy for SSL

## Next Steps

1. **Automate with cron** - Run scanner/trading at market open automatically
2. **Add alerts** - Email/SMS notifications for key events
3. **Record sessions** - Save event stream to database for analysis
4. **Mobile view** - Access dashboard from phone during market hours
5. **Cloud hosting** - Deploy WebSocket server to cloud for remote monitoring

---

**Ready for Market Open!** 🚀

Your complete automated trading system with real-time transparency is now set up.
