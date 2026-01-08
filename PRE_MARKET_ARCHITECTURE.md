# Pre-Market Preparation System - Architecture

## Overview
Two-phase system that prepares trades the night before and validates them at market open.

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 1: NIGHT PREPARATION (8 PM)                │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────┐
    │ Run Scanner  │  ← daily_scanner.py (5,405 tickers)
    └──────┬───────┘
           │
           ├─→ Score all tickers (RSI, Sharpe, Gradual Loss penalties)
           ├─→ Assign to buckets (CORE/SPEC/ASYM)
           ├─→ Save scan_results.json
           │
           ▼
    ┌──────────────────────┐
    │ Calculate Strategies │  ← trading_automation.py functions
    └──────────┬───────────┘
               │
               ├─→ BUY_HOLD: Benchmarks only (SPY/QQQ)
               ├─→ TACTICAL: Top 10 CORE
               ├─→ SPEC: 10 CORE + 5 SPECULATIVE
               ├─→ ASYM: 10 CORE + 5 SPEC + 5 ASYM
               │
               ├─→ Fetch historical data (60 days)
               ├─→ Calculate Sharpe-weighted allocations
               ├─→ Get current prices from Polygon
               │
               ▼
    ┌─────────────────────┐
    │ Save Trade Plan     │
    └─────────┬───────────┘
              │
              └─→ pending_trades.json
                  ├─→ Target allocations (4 strategies)
                  ├─→ Original composite scores
                  ├─→ Current prices
                  ├─→ Bucket assignments
                  └─→ Preparation timestamp

┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 2: MARKET OPEN VALIDATION (9 AM)                 │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────────┐
    │ Load Trade Plan  │  ← pending_trades.json
    └────────┬─────────┘
             │
             ├─→ Check age (12-14 hours overnight)
             ├─→ Load all strategies & allocations
             │
             ▼
    ┌──────────────────┐
    │ Re-Run Scanner   │  ← daily_scanner.py (fresh pre-market data)
    └────────┬─────────┘
             │
             ├─→ Get current composite scores
             ├─→ Check for overnight changes
             │
             ▼
    ┌─────────────────────┐
    │ Validate Each Pick  │  ← Score retention check
    └────────┬────────────┘
             │
             ├─→ For each ticker in each strategy:
             │   ├─→ Compare: current_score / original_score
             │   ├─→ PASS if ≥ 85% retention
             │   └─→ REJECT if < 85% retention
             │
             ├─→ Renormalize allocations after rejections
             ├─→ Calculate validation rate per strategy
             │
             ▼
    ┌─────────────────────┐
    │ Select Strategy     │  ← Choose best validated strategy
    └────────┬────────────┘
             │
             ├─→ Pick strategy with highest validation rate
             ├─→ Default to BUY_HOLD if all fail
             │
             ▼
    ┌──────────────────┐
    │ Execute Orders   │  ← trading_automation.py
    └────────┬─────────┘
             │
             ├─→ Get account value & current positions
             ├─→ Calculate position deltas
             ├─→ PHASE 1: Execute all SELL orders
             │   └─→ Wait for fills (up to 30s)
             ├─→ PHASE 2: Execute all BUY orders
             │   └─→ Use updated cash after sells
             │
             ▼
    ┌──────────────────┐
    │ Archive Results  │
    └────────┬─────────┘
             │
             └─→ archived_trades/pending_trades_YYYYMMDD_HHMMSS.json
                 ├─→ Original trade plan
                 ├─→ Validation results
                 ├─→ Rejected tickers
                 ├─→ Orders executed
                 └─→ Strategy selected
```

## Key Components

### 1. **Validation Logic**
```python
score_retention = current_score / original_score

if score_retention >= 0.85:  # 85% threshold
    ✓ ACCEPT - Execute trade
else:
    ✗ REJECT - Skip this ticker
```

### 2. **Strategy Selection**
```python
best_strategy = strategy with highest validation_rate
if validation_rate < 50%:
    fallback to BUY_HOLD  # Safest option
```

### 3. **Order Execution** (Two-Phase)
```
PHASE 1: SELLS
├─→ Place all sell orders
├─→ Wait up to 30 seconds for fills
└─→ Get updated cash balance

PHASE 2: BUYS
├─→ Use actual available cash
└─→ Place all buy orders
```

## File Structure

```
trading-system/
├── pre_market_prep.py          # Main pre-market system
├── pending_trades.json         # Overnight trade plan (temp)
├── archived_trades/            # Historical trade plans
│   └── pending_trades_*.json
├── logs/
│   └── pre_market_prep.log     # Execution logs
├── scan_results.json           # Scanner output (shared)
└── pm_state.json               # Current PM state (shared)
```

## Data Flow

### pending_trades.json Structure
```json
{
  "timestamp": "2026-01-08T20:00:00",
  "preparation_time": "2026-01-08 08:00 PM",
  "market_open_time": "2026-01-09 09:30 AM",
  "strategies": {
    "BUY_HOLD": {
      "allocations": {"SPY": 0.6, "QQQ": 0.4},
      "original_scores": {"SPY": 85.5, "QQQ": 82.3}
    },
    "TACTICAL": {...},
    "SPEC": {...},
    "ASYM": {...}
  },
  "scan_summary": {
    "total_tickers_scanned": 5405,
    "core_picks": 50,
    "spec_picks": 30,
    "asym_picks": 20
  }
}
```

### Validation Results (Added at 9 AM)
```json
{
  "validation_results": {
    "validation_time": "2026-01-09T09:00:00",
    "selected_strategy": "ASYM",
    "validated_strategies": {
      "ASYM": {
        "validated_allocations": {...},
        "rejected_tickers": ["AAPL", "MSFT"],
        "validation_rate": 0.87
      }
    },
    "orders_executed": {
      "GOOGL": 5.2,
      "NVDA": -3.1
    },
    "dry_run": false
  }
}
```

## Integration with Existing System

### Relationship to PM Scheduler (15-min)
```
8:00 PM  →  Pre-Market Prep (prepare trades)
9:00 AM  →  Pre-Market Prep (validate & execute)
9:15 AM  →  PM Scheduler (continue 15-min rotation)
9:30 AM  →  PM Scheduler
9:45 AM  →  PM Scheduler
...
```

**They work together:**
- **Pre-Market Prep**: One-time morning execution with overnight validation
- **PM Scheduler**: Continuous 15-minute re-evaluation throughout day

### Shared Components
Both systems use:
- `daily_scanner.py` - Market scanning
- `trading_automation.py` - Strategy logic & execution
- `scan_results.json` - Scanner output
- Same Alpaca account & API

## Usage Examples

### Manual Execution
```bash
# Night before (run at 8 PM)
python pre_market_prep.py --mode prepare

# Next morning (run at 9 AM)
python pre_market_prep.py --mode validate-and-execute

# Dry-run validation (test without executing)
python pre_market_prep.py --mode validate --dry-run
```

### Automated Scheduling
Add to crontab:
```bash
# Run preparation at 8 PM Mon-Fri
0 20 * * 1-5 cd /path/to/trading-system && python pre_market_prep.py --mode prepare

# Run validation at 9 AM Mon-Fri
0 9 * * 1-5 cd /path/to/trading-system && python pre_market_prep.py --mode validate-and-execute
```

## Benefits

1. **Overnight Research** - Scanner runs when you're asleep
2. **Morning Validation** - Ensures picks are still good with fresh data
3. **Rejects Degraded Picks** - Won't execute if score drops >15%
4. **Archival** - Full history of what was prepared vs executed
5. **Complements PM** - Works with 15-min scheduler for continuous optimization

## Safety Features

1. **Validation Threshold** - 85% score retention required
2. **Dry-Run Mode** - Test without executing
3. **Archive Everything** - Full audit trail
4. **Fallback Strategy** - Defaults to BUY_HOLD if validation fails
5. **Two-Phase Orders** - Sells complete before buys to prevent cash issues
