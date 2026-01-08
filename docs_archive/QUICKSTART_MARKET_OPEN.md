# Quick Start - Market Open Workflow

## 🚀 Complete Setup in 3 Steps

### Step 1: Start Local Systems (9:25 AM)

```bash
./start_trading_systems.sh
```

This launches:
- WebSocket broadcast server
- Dashboard viewer at http://localhost:8501

### Step 2: Run Trading Scripts (9:30 AM)

```bash
# Terminal 1: Scanner
python daily_scanner.py --mode scan --export scan_results.json

# Terminal 2: Trading automation  
python trading_automation.py --mode live

# Terminal 3: Profit taker
python intraday_profit_taker.py --mode aggressive
```

### Step 3: Auto-Sync to Public (Optional)

```bash
# Run once
./sync_to_cloud.sh

# OR run continuously (syncs every 60s)
./sync_to_cloud.sh --watch
```

---

## 📊 What You Get

### Local Viewer (http://localhost:8501)
- ✅ Real-time WebSocket events
- ✅ Full event details
- ✅ Live portfolio data
- ✅ Complete PM activity feed

### Public Viewer (Streamlit Cloud)
- ✅ Sanitized event feed (from public_events.json)
- ✅ Live portfolio data (Alpaca API)
- ✅ Scanner results (scan_results.json)
- ✅ Privacy-safe ($ amounts and quantities hidden)

---

## 🔒 Privacy Protection

All public events are automatically sanitized:

**Before:** `BUY 150 NVDA at $482.50 - Total: $72,375.00`  
**After:** `BUY XX NVDA at $10K-100K - Total: $10K-100K`

**Before:** `PROFIT TAKEN: TSLA +6.3% ($3,247.80)`  
**After:** `PROFIT TAKEN: TSLA +6.3% ($1K-10K)`

---

## 🛑 Stop Everything

```bash
./stop_trading_systems.sh
```

---

## 📋 Test Before Market Open

```bash
# 1. Start systems
./start_trading_systems.sh

# 2. Run test (in new terminal)
python test_broadcasting.py

# 3. Check viewer Tab 1 - should see 7 test events

# 4. Check public_events.json created
cat public_events.json | python -m json.tool | head -20

# 5. Stop systems
./stop_trading_systems.sh
```

---

## 🎯 Market Open Checklist

- [ ] 9:25 AM - Run `./start_trading_systems.sh`
- [ ] 9:25 AM - Open http://localhost:8501 in browser
- [ ] 9:30 AM - Run scanner
- [ ] 9:30 AM - Run trading automation
- [ ] 9:30 AM - Run profit taker
- [ ] 9:31 AM - Start auto-sync: `./sync_to_cloud.sh --watch`
- [ ] 4:00 PM - Run `./stop_trading_systems.sh`

**You're ready for market open! 🎉**
