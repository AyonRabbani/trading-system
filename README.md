# 🤖 Automated Trading System

**Terminal-style portfolio management with real-time monitoring and cloud sync**

A complete algorithmic trading system with market scanning, automated portfolio rebalancing, intraday profit taking, and live dashboards.

---

## 📋 Quick Start Commands

### 🔧 Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure API keys in .env
cp .env.example .env  # Then edit with your keys
```

### 🚀 Run Complete System

```bash
# Start all components in one command
./start_trading_systems.sh

# Or start individually:

# 1. Start WebSocket broadcast server (optional, for real-time events)
python log_broadcast_server.py &

# 2. Run daily market scanner
python daily_scanner.py --mode scan

# 3. Run portfolio manager (rebalancing)
python trading_automation.py --mode live          # Execute real trades
python trading_automation.py --mode dry-run       # Simulation only

# 4. Start profit taker (monitors positions)
python intraday_profit_taker.py --mode moderate   # Balanced
python intraday_profit_taker.py --mode aggressive # Tight stops
python intraday_profit_taker.py --mode conservative # Wide stops

# 5. Launch local dashboard
streamlit run local_dashboard.py --server.port=8501

# 6. Start cloud sync (for public dashboard)
./sync_to_cloud.sh --watch  # Auto-sync every 60s
```

### 🛑 Stop All Processes

```bash
./stop_trading_systems.sh

# Or kill individually:
pkill -f "log_broadcast_server"
pkill -f "intraday_profit_taker"
pkill -f "streamlit run local_dashboard"
```

---

## 📊 Dashboard Commands

### Local Dashboard (Full Features)
```bash
# Start with full API access
streamlit run local_dashboard.py

# Access at: http://localhost:8501
```

**Features:**
- Real-time account data from Alpaca API
- Live positions with P&L tracking
- Scanner results (top 20 opportunities)
- Portfolio Manager logs
- Profit Taker status
- Recent order history

### Public Dashboard (Cloud/Read-Only)
```bash
# Start public viewer (no API keys)
streamlit run public_dashboard.py

# Access at: http://localhost:8502
```

**Features:**
- System status indicators
- Sanitized activity feed
- Market scanner results
- Portfolio decisions
- Safe for public deployment (Streamlit Cloud)

---

## 🔍 Market Scanner Commands

```bash
# Basic scan (110 tickers, outputs to scan_results.json)
python daily_scanner.py --mode scan

# Scan with custom output path
python daily_scanner.py --mode scan --export custom_results.json

# Export enhanced results with backtest data
python daily_scanner.py --mode scan --export scan_results_enhanced.json

# Run backtest only (no scan)
python daily_scanner.py --mode backtest
```

**Output:**
- `scan_results.json` - Latest scan with top scorers, market regime, rotation recommendations
- Console output shows:
  - Market regime (RISK_ON, RISK_OFF, NEUTRAL)
  - Top 10 scoring tickers
  - Hot/cold sectors
  - Rotation recommendations

---

## 🤖 Portfolio Manager Commands

```bash
# Live trading (executes real orders)
python trading_automation.py --mode live

# Dry-run (simulation, no orders)
python trading_automation.py --mode dry-run

# Use scanner recommendations
python trading_automation.py --mode live --use-scanner

# Use custom scanner results
python trading_automation.py --mode live --use-scanner --scanner-path custom_results.json
```

**What it does:**
1. Loads current positions from Alpaca
2. Evaluates strategies (BUY_HOLD, MOMENTUM, SECTOR_ROTATION, etc.)
3. Selects best strategy based on Sharpe ratio
4. Calculates position deltas
5. Places orders (market orders, respects buying power)
6. Logs all activity to `trading_automation_YYYYMMDD.log`

**Strategies Available:**
- `BUY_HOLD` - SPY/QQQ 50/50
- `MOMENTUM` - Top momentum stocks
- `SECTOR_ROTATION` - Sector ETFs based on strength
- `CLASSIC_MOMENTUM` - Pre-screened high-momentum tickers
- `SPECULATIVE` - High-risk/high-reward plays
- `ASYMMETRIC` - Asymmetric risk/reward setups

---

## 💎 Profit Taker Commands

```bash
# Moderate mode (balanced, 3% trigger, 1.5% trail)
python intraday_profit_taker.py --mode moderate

# Aggressive mode (2% trigger, 1% trail)
python intraday_profit_taker.py --mode aggressive

# Conservative mode (5% trigger, 2% trail)
python intraday_profit_taker.py --mode conservative

# Custom minimum profit threshold
python intraday_profit_taker.py --mode moderate --min-profit 4.0

# Show current positions without trading
python intraday_profit_taker.py --dry-run
```

**Features:**
- Real-time monitoring via Polygon WebSocket
- Adaptive trailing stops based on volatility (ATR)
- Heartbeat updates every 5 minutes
- Time decay (tightens stops after 2pm)
- Broadcasts events to public dashboard

**Logs:**
- `profit_taker_YYYYMMDD.log` - Full activity log
- Heartbeat shows: position, price, gain %, peak price, trailing stop

---

## 🌐 Cloud Sync Commands

### Sync to GitHub for Public Dashboard

```bash
# One-time sync
./sync_to_cloud.sh

# Auto-sync every 60 seconds (continuous)
./sync_to_cloud.sh --watch

# Check sync status
tail -f /tmp/cloud_sync.log
```

**What gets synced:**
- `public_events.json` - Sanitized activity feed (no $ amounts, share counts)
- `scan_results.json` - Latest market scanner output

**Flow:**
1. Local scripts → `public_events.json` (auto-save every 30s)
2. `sync_to_cloud.sh` → Git commit & push (every 60s in watch mode)
3. GitHub → Streamlit Cloud auto-deploys (1-2 min delay)
4. Public dashboard reads updated JSON files

---

## 🔨 Process Management Commands

### Check Running Processes
```bash
# Check all trading processes
ps aux | grep -E "(daily_scanner|trading_automation|profit_taker|log_broadcast|streamlit)" | grep -v grep

# Check specific process
ps aux | grep "intraday_profit_taker" | grep -v grep

# Check port usage
lsof -ti:8501  # Local dashboard
lsof -ti:8502  # Public dashboard
lsof -ti:8765  # WebSocket server
```

### View Logs
```bash
# Tail logs in real-time
tail -f trading_automation_20260107.log
tail -f profit_taker_20260107.log
tail -f daily_scanner_20260107.log
tail -f /tmp/streamlit.log
tail -f /tmp/broadcast_server.log
tail -f /tmp/cloud_sync.log

# View last 50 lines
tail -50 trading_automation_20260107.log

# Search logs
grep "ERROR" profit_taker_20260107.log
grep "Order placed" trading_automation_20260107.log
```

### Background Process Management
```bash
# Start process in background with nohup
nohup python intraday_profit_taker.py --mode moderate > /tmp/profit_taker.log 2>&1 &

# Get process ID
echo $!

# Kill by process ID
kill <PID>

# Kill by name
pkill -f "intraday_profit_taker"

# Kill all trading processes
pkill -f "trading_automation"
pkill -f "daily_scanner"
pkill -f "intraday_profit_taker"
```

---

## 📈 Monitoring Commands

### Check Account Status
```bash
# Using Python
python -c "
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
import os

load_dotenv()
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
account = client.get_account()
print(f'Portfolio: \${float(account.equity):,.2f}')
print(f'Cash: \${float(account.cash):,.2f}')
print(f'Positions: {len(client.get_all_positions())}')
"

# Check positions
python -c "
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
import os

load_dotenv()
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
positions = client.get_all_positions()
for p in positions:
    print(f\"{p.symbol}: {p.qty} shares @ \${float(p.current_price):.2f} ({float(p.unrealized_plpc)*100:+.2f}%)\")
"
```

### Check Recent Orders
```bash
python -c "
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from dotenv import load_dotenv
import os

load_dotenv()
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
orders = client.get_orders(filter=GetOrdersRequest(status=QueryOrderStatus.ALL, limit=10))
for o in orders:
    print(f\"{o.created_at} | {o.side} {o.qty} {o.symbol} | Status: {o.status}\")
"
```

---

## 🧪 Testing Commands

```bash
# Test Alpaca connection
python -c "
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
import os

load_dotenv()
try:
    client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
    account = client.get_account()
    print(f'✅ Connected! Account: {account.status}')
except Exception as e:
    print(f'❌ Error: {e}')
"

# Test Polygon connection
python -c "
from polygon import RESTClient
from dotenv import load_dotenv
import os

load_dotenv()
try:
    client = RESTClient(os.getenv('POLYGON_API_KEY'))
    data = client.get_aggs('SPY', 1, 'day', '2024-01-01', '2024-01-02')
    print(f'✅ Polygon API working! Got {len(list(data))} bars')
except Exception as e:
    print(f'❌ Error: {e}')
"

# Test WebSocket server
python -c "
import asyncio
import websockets

async def test():
    try:
        async with websockets.connect('ws://localhost:8765') as ws:
            print('✅ WebSocket server running')
    except:
        print('❌ WebSocket server not running')

asyncio.run(test())
"
```

---

## 📂 File Structure

```
trading-system/
├── daily_scanner.py              # Market scanner (110 tickers)
├── trading_automation.py         # Portfolio manager (rebalancing)
├── intraday_profit_taker.py      # Profit taker (trailing stops)
├── event_broadcaster.py          # Event broadcasting (WebSocket + JSON)
├── public_event_exporter.py      # Sanitization for public events
├── log_broadcast_server.py       # WebSocket server
├── local_dashboard.py            # Local full-featured dashboard
├── public_dashboard.py           # Public read-only dashboard
├── sync_to_cloud.sh              # Git sync automation
├── start_trading_systems.sh      # Start all components
├── stop_trading_systems.sh       # Stop all components
├── dashboard_quickstart.sh       # Dashboard reference guide
├── .env                          # API keys (NEVER commit!)
├── requirements.txt              # Python dependencies
├── scan_results.json             # Latest scanner output
├── public_events.json            # Sanitized event feed
├── README.md                     # This file
└── logs/                         # Log files (auto-created)
    ├── trading_automation_*.log
    ├── profit_taker_*.log
    └── daily_scanner_*.log
```

---

## 🔑 Environment Variables

Required in `.env`:
```bash
# Alpaca API (Paper Trading)
ALPACA_API_KEY=your_key_here
ALPACA_SECRET_KEY=your_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets

# Polygon API (Market Data)
POLYGON_API_KEY=your_polygon_key_here
```

---

## 🎯 Common Workflows

### Daily Trading Workflow
```bash
# Morning (before market open)
python daily_scanner.py --mode scan
python trading_automation.py --mode dry-run --use-scanner  # Review plan

# Market open
python trading_automation.py --mode live --use-scanner     # Execute
python intraday_profit_taker.py --mode moderate &          # Monitor

# Monitoring
streamlit run local_dashboard.py &
tail -f profit_taker_*.log
```

### Cloud Dashboard Setup
```bash
# 1. Start auto-sync locally
./sync_to_cloud.sh --watch &

# 2. Deploy to Streamlit Cloud
# - Go to share.streamlit.io
# - Connect repo: AyonRabbani/trading-system
# - Main file: public_dashboard.py
# - Deploy (no secrets needed)

# 3. Monitor sync
tail -f /tmp/cloud_sync.log
```

### Emergency Stop
```bash
# Stop all trading activity immediately
./stop_trading_systems.sh

# Or manual:
pkill -f "trading_automation"
pkill -f "intraday_profit_taker"
pkill -f "daily_scanner"
```

---

## 📚 Additional Documentation

- **[README_DASHBOARDS.md](README_DASHBOARDS.md)** - Dashboard architecture and usage
- **[README_TRADING_AUTOMATION.md](README_TRADING_AUTOMATION.md)** - Portfolio manager details
- **[README_PROFIT_TAKER.md](README_PROFIT_TAKER.md)** - Profit taking algorithm
- **[README_SCANNER_INTEGRATION.md](README_SCANNER_INTEGRATION.md)** - Scanner usage
- **[README_CLOUD_SYNC.md](README_CLOUD_SYNC.md)** - Cloud sync setup
- **[README_DEPLOYMENT.md](README_DEPLOYMENT.md)** - Production deployment guide

---

## ⚠️ Important Notes

1. **Never commit `.env`** - Contains API keys
2. **Paper trading only** - This system uses Alpaca paper trading account
3. **Data delay** - Polygon free tier has 15-minute delay
4. **Auto-sync safety** - Public events are sanitized (no dollar amounts, share counts)
5. **Process limits** - Don't run multiple profit takers simultaneously

---

## 🐛 Troubleshooting

### Dashboard shows "Idle"
```bash
# Events may be too old (> 1 hour)
# Restart profit taker to generate fresh heartbeats
pkill -f "intraday_profit_taker"
python intraday_profit_taker.py --mode moderate &

# Check event file timestamp
ls -lh public_events.json
tail public_events.json
```

### Scanner not displaying stocks
```bash
# Check scan_results.json exists
ls -lh scan_results.json

# Verify JSON structure
python -c "import json; print(json.load(open('scan_results.json'))['top_scorers'][:3])"

# Re-run scanner
python daily_scanner.py --mode scan
```

### Orders not executing
```bash
# Check market hours
python -c "
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
import os

load_dotenv()
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
clock = client.get_clock()
print(f'Market open: {clock.is_open}')
"

# Check buying power
python -c "
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv
import os

load_dotenv()
client = TradingClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'), paper=True)
account = client.get_account()
print(f'Buying power: \${float(account.buying_power):,.2f}')
"

# Check logs
grep "ERROR" trading_automation_*.log
```

---

## 📞 Support

- **Documentation**: Check README files in repo
- **Logs**: All activity logged to timestamped files
- **Dashboard**: http://localhost:8501 for live monitoring

---

**Status**: ✅ Fully operational with terminal-style dashboards and cloud sync
**Last Updated**: January 7, 2026
