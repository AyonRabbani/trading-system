# Trading Automation System

Automated daily portfolio rebalancing system that selects the best performing strategy and executes orders via Alpaca API.

## 🎯 Overview

This script consolidates the essential trading logic from `TradingSystem.ipynb` into a standalone automation tool that:

1. **Loads market data** from Polygon API for all ticker groups
2. **Runs simplified backtests** for each strategy (Buy-Hold, Tactical, Speculative, Asymmetric)
3. **Selects best strategy** based on highest NAV
4. **Calculates position deltas** between target and current positions
5. **Places orders** via Alpaca (MOO orders if market closed, immediate if open)

## 📋 Ticker Groups

The system manages four groups of tickers:

- **Core Tickers**: `GLD`, `SLX`, `JEF`, `CPER`
- **Benchmarks**: `SPY`, `QQQ`
- **Speculative**: `NVDA`, `PLTR`, `TSLA`, `MSFT`
- **Asymmetric**: `OKLO`, `RMBS`, `QBTS`, `IREN`, `AFRM`, `SOFI`

## 🚀 Usage

### Dry Run (Recommended First)

Test the system without placing actual orders:

```bash
python trading_automation.py --mode dry-run
```

This will:
- Load all market data
- Run strategy backtests
- Select best strategy
- Calculate position deltas
- Show what orders WOULD be placed (but won't actually place them)

### Live Execution

Place actual orders to Alpaca:

```bash
python trading_automation.py --mode live
```

**Important**: This will place real orders in your Alpaca account!

### Custom Ticker Groups

Override the ticker groups:

```bash
python trading_automation.py --mode dry-run --tickers GLD,SLX,SPY,QQQ
```

## 🔧 Configuration

Edit these variables in the script to customize:

```python
# Backtest Parameters
CAPITAL = 100000              # Virtual backtest capital (for scaling)
LOOKBACK_DAYS = 10           # Days to look back for momentum
SHARPE_LOOKBACK = 30         # Period for Sharpe ratio calculation
COOLDOWN_DAYS = 5            # Days to wait between rebalances
DRAWDOWN_THRESHOLD = 0.10    # Max drawdown threshold (10%)
PM_MOMENTUM_LOOKBACK = 10    # Portfolio Manager momentum period
```

## 📊 Strategy Selection Logic

The system runs four strategies:

1. **BUY_HOLD**: Simple benchmark holding (SPY, QQQ)
2. **TACTICAL**: Core tickers + Benchmarks
3. **SPEC**: Tactical + Speculative tickers
4. **ASYM**: All tickers including asymmetric bets

For each strategy:
- Calculates Sharpe ratios over lookback period
- Selects top 3 tickers by Sharpe
- Allocates equal weight
- Computes final NAV

The strategy with **highest NAV** wins and its positions become the rebalancing target.

## 🔄 Order Execution

### Market Closed (Default)
- Places **MOO (Market-on-Open)** orders
- Orders execute at next market open (9:30 AM ET)
- Ideal for running after market close (4:15 PM ET)

### Market Open
- Places **immediate market orders**
- Orders execute right away
- Use when running during trading hours

### Position Sizing
- Target positions scaled from backtest capital ($100K) to actual account value
- Applies 2% tolerance (won't trade if delta < 2% of target)
- Validates buying power before placing buy orders
- Scales down buy orders proportionally if insufficient cash

## 📝 Logging

All activity logged to:
- **Console**: Real-time progress
- **File**: `trading_automation_YYYYMMDD.log`

Log includes:
- Market data loading
- Strategy backtest results
- Account status
- Position deltas
- Order placements
- Errors (if any)

## ⚠️ Important Notes

1. **Paper Trading**: Currently configured for Alpaca Paper account
2. **API Keys**: Hardcoded in script (consider using environment variables for production)
3. **Dry Run First**: Always test with `--mode dry-run` before live execution
4. **Market Hours**: Script automatically detects market status and adjusts order types
5. **Whole Shares**: All orders rounded to whole shares (no fractional trading)

## 🔐 Security

For production use, consider:

```python
import os

ALPACA_API_KEY = os.environ.get('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
POLYGON_API_KEY = os.environ.get('POLYGON_API_KEY')
```

Then set environment variables:
```bash
export ALPACA_API_KEY="your_key"
export ALPACA_SECRET_KEY="your_secret"
export POLYGON_API_KEY="your_polygon_key"
```

## 📅 Recommended Schedule

**Best Practice**: Run after market close

```bash
# Run at 4:30 PM ET every weekday
30 16 * * 1-5 cd /path/to/script && python trading_automation.py --mode live
```

This places MOO orders that execute at next open (9:30 AM ET).

## 🐛 Troubleshooting

**No market data loaded**
→ Check Polygon API key and network connection

**"Insufficient buying power" errors**
→ Script automatically scales down buy orders to fit available cash

**Orders not executing**
→ Check Alpaca account status and order logs in Alpaca dashboard

**Strategy selection seems wrong**
→ Review backtest parameters (LOOKBACK_DAYS, SHARPE_LOOKBACK)

## 🔄 Integration with Intraday Profit Taker

Typical workflow:

1. **After market close (4:30 PM)**: Run `trading_automation.py --mode live`
   - Places MOO orders for next day

2. **At market open (9:30 AM)**: Orders execute automatically

3. **During trading day**: Run `intraday_profit_taker.py --mode moderate`
   - Monitors positions
   - Takes profits with trailing stops

4. **Repeat daily**

## 📚 Differences from TradingSystem.ipynb

**Removed**:
- Detailed backtest visualizations
- Monthly performance analysis
- Strategy comparison charts
- Cooldown period tracking
- Drawdown monitoring
- Portfolio composition analysis

**Kept**:
- Core strategy logic
- Sharpe-based ticker selection
- Position scaling
- Buying power validation
- Order execution with MOO support
- Market-aware order placement

**Simplified**:
- Backtests now simple equal-weight allocations
- Strategy selection based on NAV only (not momentum scores)
- No historical tracking (just current state)

This makes the script **much faster** and focused purely on daily rebalancing.

## 🚀 Quick Start Example

```bash
# 1. First time: Dry run to test
python trading_automation.py --mode dry-run

# 2. Review the log file
cat trading_automation_20260106.log

# 3. If everything looks good, go live
python trading_automation.py --mode live

# 4. Check Alpaca dashboard to confirm orders
```

## 💡 Tips

- Run in **dry-run mode** at least once per day to verify strategy selection
- Monitor log files for any errors or warnings
- Keep backtest parameters aligned with your risk tolerance
- Review executed orders in Alpaca dashboard regularly
- Combine with `intraday_profit_taker.py` for complete automation

---

**Happy Trading! 📈💰**
