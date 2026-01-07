# Scanner Integration Guide

## 🔄 Daily Workflow: Scanner → Trading Automation

### **Overview**
The `daily_scanner.py` identifies optimal ticker rotations, and `trading_automation.py` executes the Portfolio Manager strategy with those tickers.

---

## 📋 Two-Step Workflow

### **Step 1: Run Daily Scanner**
Scans 110+ tickers, tests portfolio sizes, compares metrics, and generates recommendations.

```bash
# Run full scan with analytics
python daily_scanner.py --mode scan --export scan_results_enhanced.json
```

**Output:**
- Portfolio size optimization (5, 10, 15, 20, 30 tickers tested)
- Current vs Recommended portfolio comparison
- Sharpe/Return/Volatility/Drawdown metrics
- Specific rotation recommendations
- Complete recommended portfolio for each group

**Key Metrics Displayed:**
```
Portfolio Size Testing:
  Size  5: Sharpe=2.238, Return=107.1%, Vol=47.9%, MaxDD=-36.2%
  Size 10: Sharpe=2.705, Return=100.0%, Vol=37.0%, MaxDD=-26.9% ← OPTIMAL

Portfolio Comparison:
  Current:      Sharpe=1.269, Return=38.5%, MaxDD=-25.6%
  Recommended:  Sharpe=2.306, Return=80.4%, MaxDD=-27.7%
  Improvement:  +1.037 Sharpe (+82%)

Recommended Portfolio:
  CORE:        RKLB, AA, MU, FCX
  SPECULATIVE: QBTS, COPX, LRCX, XME
  ASYMMETRIC:  PLTR, PFSI, INTC, GOOGL
```

---

### **Step 2: Run Trading Automation with Scanner Recommendations**

#### **Option A: Auto-Load Scanner Results** ✅ (Recommended)
```bash
# Load recommendations and execute Portfolio Manager strategy
python trading_automation.py --mode dry-run --use-scanner
```

**What Happens:**
1. Loads `scan_results_enhanced.json`
2. Updates ticker groups with scanner recommendations
3. Runs 4 strategy backtests (BUY_HOLD, TACTICAL, SPEC, ASYM)
4. Portfolio Manager selects best strategy
5. Calculates position deltas
6. Places MOO/immediate orders

**Output:**
```
PHASE 0: LOADING SCANNER RECOMMENDATIONS
  Expected Sharpe Improvement: +1.037
  Expected Return Improvement: +41.9%
  Recommended Portfolio:
    CORE: RKLB, AA, MU, FCX
    SPECULATIVE: QBTS, COPX, LRCX, XME
    ASYMMETRIC: PLTR, PFSI, INTC, GOOGL
  ✓ Scanner recommendations applied

PHASE 3: STRATEGY SELECTION
  BUY_HOLD: NAV $100,000.00, 2 positions
  TACTICAL: NAV $105,432.15, 3 positions
  SPEC: NAV $112,847.92, 3 positions
  ASYM: NAV $118,523.44, 3 positions
  ✓ Selected: ASYM (NAV: $118,523.44)
```

#### **Option B: Manual Ticker Override** (For testing)
```bash
# Test specific tickers without scanner
python trading_automation.py --mode dry-run --tickers RKLB,AA,MU,FCX,QBTS
```

---

## 🎯 Complete Daily Automation

### **Recommended Schedule** (via cron)

```bash
# Add to crontab (crontab -e)

# 4:00 PM ET - Run scanner after market close
00 16 * * 1-5 cd /path/to/Research && python daily_scanner.py --mode scan --export scan_results_enhanced.json >> scanner.log 2>&1

# 4:30 PM ET - Execute trading automation with scanner results
30 16 * * 1-5 cd /path/to/Research && python trading_automation.py --mode live --use-scanner >> trading.log 2>&1

# 9:30 AM ET - Start intraday profit taker when market opens
30 09 * * 1-5 cd /path/to/Research && python intraday_profit_taker.py --mode moderate >> profit_taker.log 2>&1 &
```

---

## 📊 Decision Flow

```
Daily Scan (4:00 PM)
  ├─> Load 110+ tickers from screening universe
  ├─> Score all tickers (momentum, volatility, RS, breakout, volume)
  ├─> Test portfolio sizes (5, 10, 15, 20, 30)
  ├─> Assign to groups (CORE, SPECULATIVE, ASYMMETRIC)
  ├─> Compare current vs recommended
  └─> Export results to scan_results_enhanced.json

Trading Automation (4:30 PM)
  ├─> Load scanner recommendations
  ├─> Update ticker groups (CORE, SPECULATIVE, ASYMMETRIC)
  ├─> Run 4 strategy backtests with new tickers
  ├─> Portfolio Manager selects best strategy
  ├─> Calculate position deltas (scale to account size)
  ├─> Validate buying power
  └─> Place MOO orders (execute at 9:30 AM next day)

Intraday Profit Taker (9:30 AM - 4:00 PM)
  ├─> Monitor all open positions via WebSocket
  ├─> Track adaptive trailing stops
  ├─> Take profits when stops hit
  └─> Log all trades
```

---

## 🔑 Key Integration Features

### **1. Automatic Ticker Updates**
Scanner recommendations automatically update:
- `CORE_TICKERS` → Scanner's CORE group
- `SPECULATIVE` → Scanner's SPECULATIVE group  
- `ASYMMETRIC` → Scanner's ASYMMETRIC group
- `BENCHMARKS` → Always SPY, QQQ (static)

### **2. Portfolio Manager Strategy Selection**
After loading new tickers, PM runs backtests:
- **BUY_HOLD**: Benchmarks only (SPY, QQQ)
- **TACTICAL**: CORE + Benchmarks
- **SPEC**: CORE + Benchmarks + SPECULATIVE
- **ASYM**: All groups (CORE + SPEC + ASYM + Benchmarks)

PM selects strategy with **highest NAV** from backtests.

### **3. Risk Management**
- Buying power validation (scales down if insufficient)
- Position sizing tolerance (2% threshold)
- Historical price fallback (when market closed)

---

## 📁 File Structure

```
Research/
├── daily_scanner.py              # Opportunity scanner
├── trading_automation.py         # Portfolio Manager automation
├── intraday_profit_taker.py      # Profit taking during day
├── scan_results_enhanced.json    # Scanner output (auto-generated)
├── trading_automation_YYYYMMDD.log
├── daily_scanner_YYYYMMDD.log
└── profit_taker_YYYYMMDD.log
```

---

## 🎨 Usage Examples

### **Example 1: Daily Production Run**
```bash
# Morning: Check scanner results from yesterday
cat scan_results_enhanced.json | python -m json.tool | less

# Review recommendations
python daily_scanner.py --mode scan --export scan_results_enhanced.json

# Execute with scanner recommendations
python trading_automation.py --mode live --use-scanner

# Start profit taker
python intraday_profit_taker.py --mode moderate &
```

### **Example 2: Testing New Strategy**
```bash
# Run scanner with custom rotation threshold
python daily_scanner.py --mode scan --threshold 30.0 --export test_scan.json

# Test with scanner results in dry-run
python trading_automation.py --mode dry-run --use-scanner --scanner-results test_scan.json

# Compare results
diff scan_results_enhanced.json test_scan.json
```

### **Example 3: Emergency Override**
```bash
# Market crash - use defensive tickers only
python trading_automation.py --mode live --tickers GLD,TLT,UUP,DBA
```

---

## 🚨 Safeguards

### **Scanner Quality Checks**
- Minimum 60 days of data per ticker
- Sharpe ratio threshold for recommendations
- Drawdown limits per portfolio size
- Sector rotation signals (RISK_ON/RISK_OFF/NEUTRAL)

### **Trading Automation Checks**
- Dry-run mode for testing
- Buying power validation
- Price availability checks (fallback to historical)
- Order execution confirmation
- Comprehensive logging

### **Manual Override Options**
```bash
# Use default tickers (ignore scanner)
python trading_automation.py --mode dry-run

# Use specific tickers
python trading_automation.py --mode dry-run --tickers NVDA,AMD,AVGO,TSM

# Use scanner from specific file
python trading_automation.py --mode dry-run --use-scanner --scanner-results backup_scan.json
```

---

## 📈 Performance Tracking

Monitor the integration effectiveness:

```bash
# Compare scanner recommendations vs actual execution
tail -f trading_automation_20260107.log | grep "Selected:"

# Check Sharpe improvement realization
python -c "
import json
scan = json.load(open('scan_results_enhanced.json'))
print('Expected Sharpe:', scan['portfolio_comparison']['recommended']['sharpe'])
print('Expected Return:', scan['portfolio_comparison']['recommended']['annual_return'])
"
```

---

## 🔧 Troubleshooting

### **Issue: Scanner results not loading**
```bash
# Check if file exists
ls -lh scan_results_enhanced.json

# Validate JSON format
python -m json.tool scan_results_enhanced.json
```

### **Issue: Tickers not updating**
```bash
# Check scanner output
python daily_scanner.py --mode scan | grep "Recommended Portfolio"

# Verify integration
python trading_automation.py --mode dry-run --use-scanner | grep "PHASE 0"
```

### **Issue: Poor performance**
```bash
# Run scanner with higher threshold
python daily_scanner.py --mode scan --threshold 35.0

# Review size optimization
python daily_scanner.py --mode scan | grep "PORTFOLIO SIZE TESTING" -A 10
```

---

## 🎯 Best Practices

1. **Run scanner daily at 4:00 PM** (after market close, before automation)
2. **Review recommendations** before live execution (check Sharpe improvement)
3. **Use dry-run first** when testing new configurations
4. **Monitor logs** for execution issues
5. **Keep scanner results history** (compare week-over-week)
6. **Set minimum improvement threshold** (e.g., +0.3 Sharpe) before rotating
7. **Combine with profit taker** for complete automation

---

## 📞 Integration Summary

| Component | When | Purpose |
|-----------|------|---------|
| `daily_scanner.py` | 4:00 PM | Identify optimal tickers |
| `trading_automation.py` | 4:30 PM | Execute PM strategy with new tickers |
| `intraday_profit_taker.py` | 9:30 AM - 4:00 PM | Take profits during day |

**Complete automation:** Scanner finds tickers → PM selects strategy → Profit taker manages exits → Repeat daily
