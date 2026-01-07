# Intraday Profit Taker

Automated intraday profit-taking system with adaptive trailing stops based on statistical analysis.

## 🎯 Features

- **Real-time monitoring** via Polygon WebSocket (minute bars)
- **Adaptive trailing stops** based on ATR and volatility
- **Statistical analysis** to optimize stop placement per ticker
- **Time-decay logic** (tighter stops as market close approaches)
- **Three trading modes** (aggressive, moderate, conservative)
- **Automatic position management** via Alpaca API
- **Comprehensive logging** and performance tracking
- **Heartbeat monitoring** - 60-second status updates even when WebSocket is quiet
- **Alpaca polling fallback** - Queries REST API every 30 seconds as backup data source
- **Colorful terminal UI** - Green for profits, red for losses, visual status indicators
- **Live staleness tracking** - Shows time since last update for each position

## 📋 Requirements

```bash
pip install numpy pandas requests massive-python-sdk
```

## 🚀 Quick Start

### 1. View Current Positions (Dry Run)
```bash
python intraday_profit_taker.py --dry-run
```

### 2. Start Monitoring (Moderate Mode)
```bash
python intraday_profit_taker.py
```

### 3. Aggressive Mode (Faster Profit Taking)
```bash
python intraday_profit_taker.py --mode aggressive
```

### 4. Conservative Mode with Custom Threshold
```bash
python intraday_profit_taker.py --mode conservative --min-profit 5.0
```

## 🎛️ Trading Modes

### Aggressive Mode
- **Profit Threshold:** 2%
- **Trailing Stop:** 1% - 3%
- **Volatility Multiplier:** 1.5x ATR
- **Best for:** High-momentum stocks, quick scalps

### Moderate Mode (Default)
- **Profit Threshold:** 3%
- **Trailing Stop:** 1.5% - 4%
- **Volatility Multiplier:** 2.0x ATR
- **Best for:** Balanced approach, typical trades

### Conservative Mode
- **Profit Threshold:** 5%
- **Trailing Stop:** 2% - 5%
- **Volatility Multiplier:** 2.5x ATR
- **Best for:** Letting winners run, swing trades

## 📊 How It Works

### 1. **Initialization**
- Connects to Alpaca and loads current positions
- Checks market status (only runs during market hours)
- Subscribes to Polygon WebSocket for real-time minute bars

### 2. **Statistical Analysis**
For each position, continuously calculates:
- **ATR (Average True Range):** Measures typical price movement
- **Volatility:** Standard deviation of recent returns
- **Adaptive Trail Width:** `ATR / Price × Volatility Multiplier`

### 3. **Profit-Taking Logic**

```
Entry: $100
Price rises to $103 (+3%) → Activates trailing stop

ATR = $0.50, Current Price = $103
Trail Width = ($0.50 / $103) × 2.0 = 0.97% ≈ 1%
Trailing Stop = $103 × (1 - 0.01) = $102.00

Price rises to $105 → Stop moves to $103.95
Price drops to $103.95 → SELL (profit taken)
```

### 4. **Time Decay**
After 2:00 PM ET, trailing stops tighten by 20-30% to lock in profits before close.

### 5. **Force Exit**
At 3:55 PM, any position with >1% gain is automatically closed.

## 📈 Example Output

```
================================================================================
INITIALIZING INTRADAY PROFIT TAKER
================================================================================
Mode: MODERATE
Profit Threshold: 3.0%
Trailing Stop Range: 1.5% - 4.0%

✓ Market is OPEN

Found 4 positions:
--------------------------------------------------------------------------------
GLD    |     58 shares @ $ 412.50 | Current: $ 415.20 | P&L: $  156.60 (+0.65%)
JEF    |    562 shares @ $  70.00 | Current: $  71.50 | P&L: $  843.00 (+2.14%)
CPER   |    786 shares @ $  37.27 | Current: $  37.80 | P&L: $  416.58 (+1.42%)
SLX    |    386 shares @ $  88.58 | Current: $  89.20 | P&L: $  239.32 (+0.70%)
--------------------------------------------------------------------------------

Starting WebSocket connection...
Subscribing to: AM.GLD, AM.JEF, AM.CPER, AM.SLX
✓ WebSocket connected and subscribed

================================================================================
MONITORING STARTED - Watching for profit opportunities...
================================================================================

🎯 JEF | TRAILING ACTIVATED at +3.21% | Peak: $72.25 | Stop: $71.17 (1.5% trail) | ATR: $0.432 | Vol: 0.82%

📈 JEF | NEW PEAK $72.80 (+4.00%) | Stop raised to $71.71

================================================================================
⏱️  HEARTBEAT UPDATE - 02:15:30 PM
================================================================================
GLD    | Status: WATCHING | Price: $415.20 | Gain: +0.65% | Peak: $415.80 | Updated (2m ago)
CPER   | Status: WATCHING | Price: $37.85 | Gain: +1.56% | Peak: $37.90 | Updated (1m ago)
SLX    | Status: TRAILING | Price: $90.15 | Gain: +1.77% | Peak: $90.50 | Updated (just now)
       └─ Stop: $89.14 (1.1% away)
================================================================================

💰 TAKING PROFIT: JEF
--------------------------------------------------------------------------------
Entry:     $70.00
Peak:      $72.80 (+4.00%)
Exit:      $71.70
Gain:      +2.43%
Profit:    $955.40
Shares:    562
Hold Time: 0:47:23
Order ID:  a7b8c9d0-1234-5678-9abc-def012345678
✓ Position closed successfully
================================================================================

📊 SESSION STATISTICS:
   Profits Taken:   1
   Total Profit:    $955.40
   Average Gain:    2.43%
   Avg Hold Time:   47 minutes
   Active Positions: 3
```

## 🔧 Configuration

Edit the script to customize:

```python
# API Keys (lines 19-22)
POLYGON_API_KEY = "your_key"
ALPACA_API_KEY = "your_key"
ALPACA_SECRET_KEY = "your_secret"

# Trading Modes (lines 25-49)
MODES = {
    'aggressive': {
        'profit_threshold': 0.02,
        'min_trailing_stop': 0.01,
        # ... customize
    }
}
```

## 📝 Logs

All activity is logged to:
- **Console:** Real-time updates with color coding
- **File:** `profit_taker_YYYYMMDD.log`

## 🎨 Terminal UI Features

The script uses ANSI color codes for enhanced readability:

- **🟢 Green:** Profits, gains, successful operations
- **🔴 Red:** Losses, errors, warnings
- **🔵 Cyan:** Info messages, headers, statistics
- **🟡 Yellow:** Cautions, market closed, force exits
- **⚪ Gray:** Timestamps, staleness indicators

### Heartbeat Monitoring

The system prints status updates every 60 seconds showing:
- Current position status (WATCHING vs TRAILING)
- Latest prices and gains
- Time since last data update (staleness tracking)
- Distance to trailing stop trigger

This ensures you know the system is alive even when WebSocket is quiet (common with delayed feeds or thinly-traded stocks).

### Alpaca Polling Fallback

When the Polygon WebSocket is inactive (15-minute delayed feed + thin trading), the system automatically polls the Alpaca REST API every 60 seconds to:
- Fetch current position prices
- Update tracking data
- Ensure positions aren't missed

This dual-source approach provides reliable monitoring even with free data feeds.

## ⚠️ Important Notes

1. **Market Hours Only:** Script only runs during market hours (9:30 AM - 4:00 PM ET)
2. **Paper Trading:** Currently configured for Alpaca Paper account
3. **Real-time Data:** Uses Polygon delayed feed (15-minute delay)
4. **Position Monitoring:** Only monitors positions already in Alpaca account
5. **No New Entries:** Does not open new positions, only manages exits

## 🛡️ Risk Management

The algorithm includes multiple safety features:

- ✅ Never trails below entry price (no losses locked in)
- ✅ Minimum profit threshold before activation
- ✅ Adaptive stops based on volatility (less whipsaw)
- ✅ Time-decay logic (tighter stops near close)
- ✅ Force exit before close (no overnight risk)
- ✅ Statistical validation (requires 14+ bars for ATR)

## 🔄 Integration with TradingSystem.ipynb

Typical workflow:

1. **Morning (9:30 AM):** Run `daily_rebalance()` in notebook
2. **Start Monitoring:** `python intraday_profit_taker.py --mode moderate`
3. **Let it run:** Script monitors all day, takes profits automatically
4. **Next Morning:** Repeat

## 📊 Performance Tracking

Statistics tracked per session:
- Number of profits taken
- Total profit (dollars and %)
- Average gain per trade
- Average hold time
- Individual trade details

## 🐛 Troubleshooting

**"No positions found"**
→ Make sure you have active positions in Alpaca first

**"Market is CLOSED"**
→ Script only runs during market hours

**WebSocket connection issues**
→ Check Polygon API key and network connection

**"Position not found" errors**
→ Position may have been closed manually in Alpaca

## 📚 Command Line Options

```
usage: intraday_profit_taker.py [-h] [--mode {aggressive,moderate,conservative}]
                                 [--min-profit PCT] [--dry-run]

optional arguments:
  -h, --help            show this help message and exit
  --mode {aggressive,moderate,conservative}
                        Trading mode (default: moderate)
  --min-profit PCT      Minimum profit % to start trailing (overrides mode default)
  --dry-run             Show positions but do not trade
```

## 🎓 Statistical Analysis Explained

### ATR (Average True Range)
Measures typical price movement over recent bars. Used to set trail width that adapts to each stock's behavior.

- **Low ATR stocks** (stable): Tighter trailing stops
- **High ATR stocks** (volatile): Wider trailing stops

### Volatility (Return Std Dev)
Measures price oscillation frequency. Prevents premature exits on choppy stocks.

### Adaptive Formula
```
Trail Width = (ATR / Current Price) × Volatility Multiplier
Clamped between: [min_trailing_stop, max_trailing_stop]
```

This ensures:
- Volatile stocks get wider stops (avoid whipsaw)
- Stable stocks get tighter stops (lock profits faster)
- Each stock gets optimal treatment

## 💡 Tips for Best Results

1. **Start Conservative:** Use conservative mode until comfortable
2. **Monitor First Day:** Watch logs to understand behavior
3. **Adjust Based on Results:** Fine-tune thresholds per your style
4. **Don't Overtrade:** Not every position needs to be closed today
5. **Combine with PM:** Let Portfolio Manager pick entries, this handles exits
6. **Review Logs:** Analyze what worked and adjust modes

## 🚀 Advanced Usage

### Multiple Modes Simultaneously
Run different modes on different positions by filtering:

```python
# In the script, add position filtering
if ticker in ['NVDA', 'PLTR', 'TSLA']:
    config = MODES['aggressive']
else:
    config = MODES['conservative']
```

### Custom ATR Periods
Adjust the `maxlen` in `PositionTracker`:

```python
price_history: deque = field(default_factory=lambda: deque(maxlen=200))  # More history
```

### Webhook Alerts
Add notification when profits are taken:

```python
def _take_profit(self, ticker: str, price: float, gain_pct: float):
    # ... existing code ...
    
    # Send webhook
    requests.post('https://your-webhook.com', json={
        'ticker': ticker,
        'profit': profit_dollars,
        'gain': gain_pct
    })
```

## 📧 Support

For issues or questions, check the logs first. Most problems are logged with detailed error messages.

---

**Happy Trading! 📈💰**
