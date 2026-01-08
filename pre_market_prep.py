#!/usr/bin/env python3
"""
Pre-Market Preparation System

Night Before (8 PM):
- Run full scanner
- Identify top picks for tomorrow
- Calculate target allocations
- Save as "pending_trades.json"

Market Open (9:00 AM):
- Re-validate picks with pre-market data
- Check if fundamentals still align
- Execute validated trades
- Archive invalid picks

Usage:
    # Night before (8 PM)
    python pre_market_prep.py --mode prepare
    
    # Market open (9 AM)
    python pre_market_prep.py --mode validate-and-execute
    
    # Dry-run validation only
    python pre_market_prep.py --mode validate --dry-run
"""

import os
import json
import logging
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from dotenv import load_dotenv

# Import existing modules
from daily_scanner import load_ticker_universe
from trading_automation import (
    AlpacaClient, fetch_price_history, calculate_indicators,
    calculate_sharpe_weighted_allocation, load_dynamic_buckets_from_scanner
)

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================

POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

PENDING_TRADES_FILE = 'pending_trades.json'
VALIDATION_THRESHOLD = 0.85  # 85% score retention to pass validation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/pre_market_prep.log'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# PHASE 1: PREPARE TRADES (Night Before - 8 PM)
# ============================================================================

def prepare_next_day_trades():
    """
    Run full scanner and prepare trades for next morning
    Saves pending_trades.json with:
    - Target allocations
    - Original scores
    - Timestamp
    - Market conditions
    """
    logging.info("="*80)
    logging.info("PRE-MARKET PREPARATION - SCANNING FOR TOMORROW'S TRADES")
    logging.info("="*80)
    
    # Import scanner function
    from daily_scanner import run_full_scan
    
    # Run full scanner
    logging.info("\n[1/4] Running full market scan...")
    scan_results = run_full_scan()
    
    if not scan_results:
        logging.error("Scanner failed, aborting preparation")
        return False
    
    # Load buckets
    logging.info("\n[2/4] Loading strategy buckets...")
    buckets = load_dynamic_buckets_from_scanner()
    
    # Calculate target allocations for each strategy
    logging.info("\n[3/4] Calculating target allocations...")
    
    # Get latest prices for all tickers
    all_tickers = []
    for bucket_name, ticker_list in buckets.items():
        all_tickers.extend(ticker_list)
    all_tickers = list(set(all_tickers))
    
    # Fetch current prices
    current_prices = {}
    for ticker in all_tickers:
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={POLYGON_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if 'results' in data and len(data['results']) > 0:
                current_prices[ticker] = data['results'][0]['c']
        except Exception as e:
            logging.warning(f"Could not fetch price for {ticker}: {e}")
    
    # Prepare trade recommendations for each strategy
    trade_plan = {
        'timestamp': datetime.now().isoformat(),
        'preparation_time': datetime.now().strftime('%Y-%m-%d %I:%M %p'),
        'market_open_time': (datetime.now() + timedelta(days=1)).replace(hour=9, minute=30).strftime('%Y-%m-%d %I:%M %p'),
        'buckets': buckets,
        'strategies': {},
        'current_prices': current_prices,
        'scan_summary': {
            'total_tickers_scanned': len(scan_results.get('all_scores', [])),
            'core_picks': len(buckets.get('CORE', [])),
            'spec_picks': len(buckets.get('SPECULATIVE', [])),
            'asym_picks': len(buckets.get('ASYMMETRIC', []))
        }
    }
    
    # Get historical data for allocation calculation
    logging.info("  Loading historical data for allocation weights...")
    data = {}
    for ticker in all_tickers[:30]:  # Limit to avoid timeout
        df = fetch_price_history(ticker, 60)
        if not df.empty:
            df = calculate_indicators(df, 30)
            data[ticker] = df
    
    if not data:
        logging.error("No historical data loaded")
        return False
    
    common_dates = sorted(set.intersection(*[set(df.index) for df in data.values()]))
    latest_date = common_dates[-1] if common_dates else None
    
    if not latest_date:
        logging.error("No common dates found")
        return False
    
    # Calculate allocations for each strategy
    strategy_configs = {
        'BUY_HOLD': {
            'tickers': buckets['BENCHMARKS'],
            'description': 'Sharpe-weighted benchmarks only'
        },
        'TACTICAL': {
            'tickers': buckets.get('CORE', [])[:10],
            'description': 'Top 10 CORE tickers with rotation'
        },
        'SPEC': {
            'tickers': buckets.get('CORE', [])[:10] + buckets.get('SPECULATIVE', [])[:5],
            'description': '85% CORE + 15% SPECULATIVE'
        },
        'ASYM': {
            'tickers': buckets.get('CORE', [])[:10] + buckets.get('SPECULATIVE', [])[:5] + buckets.get('ASYMMETRIC', [])[:5],
            'description': 'Full 3-tier allocation'
        }
    }
    
    for strategy_name, config in strategy_configs.items():
        logging.info(f"  Calculating {strategy_name} allocation...")
        
        # Filter tickers with data
        available_tickers = [t for t in config['tickers'] if t in data]
        
        if available_tickers:
            allocations = calculate_sharpe_weighted_allocation(available_tickers, data, latest_date)
            
            trade_plan['strategies'][strategy_name] = {
                'description': config['description'],
                'allocations': allocations,
                'tickers': available_tickers,
                'original_scores': {
                    ticker: next((s['composite_score'] for s in scan_results.get('all_scores', []) 
                                if s['ticker'] == ticker), 0)
                    for ticker in available_tickers
                }
            }
            
            logging.info(f"    ✓ {len(allocations)} positions, top 3: {list(allocations.items())[:3]}")
    
    # Save pending trades
    logging.info(f"\n[4/4] Saving pending trades to {PENDING_TRADES_FILE}...")
    with open(PENDING_TRADES_FILE, 'w') as f:
        json.dump(trade_plan, f, indent=2)
    
    logging.info("\n" + "="*80)
    logging.info("✅ PREPARATION COMPLETE")
    logging.info("="*80)
    logging.info(f"Prepared for: {trade_plan['market_open_time']}")
    logging.info(f"Strategies ready: {len(trade_plan['strategies'])}")
    logging.info(f"Run validation at 9 AM: python pre_market_prep.py --mode validate-and-execute")
    logging.info("="*80)
    
    return True

# ============================================================================
# PHASE 2: VALIDATE & EXECUTE (9 AM Market Open)
# ============================================================================

def validate_and_execute_trades(dry_run: bool = True):
    """
    Validate pending trades against current market conditions
    Execute only trades that pass validation threshold
    """
    logging.info("="*80)
    logging.info("PRE-MARKET VALIDATION - CHECKING OVERNIGHT PICKS")
    logging.info("="*80)
    
    # Load pending trades
    if not os.path.exists(PENDING_TRADES_FILE):
        logging.error(f"No pending trades found: {PENDING_TRADES_FILE}")
        logging.info("Run preparation first: python pre_market_prep.py --mode prepare")
        return False
    
    with open(PENDING_TRADES_FILE, 'r') as f:
        trade_plan = json.load(f)
    
    prep_time = trade_plan['preparation_time']
    logging.info(f"Loaded trade plan from: {prep_time}")
    logging.info(f"Time elapsed: {(datetime.now() - datetime.fromisoformat(trade_plan['timestamp'])).total_seconds() / 3600:.1f} hours")
    
    # Re-scan all tickers to get current scores
    logging.info("\n[1/4] Re-scanning tickers with latest data...")
    from daily_scanner import run_full_scan
    
    current_scan = run_full_scan()
    if not current_scan:
        logging.error("Current scan failed, aborting validation")
        return False
    
    current_scores = {s['ticker']: s['composite_score'] for s in current_scan.get('all_scores', [])}
    
    # Validate each strategy's picks
    logging.info("\n[2/4] Validating picks against current scores...")
    validated_strategies = {}
    
    for strategy_name, strategy_data in trade_plan['strategies'].items():
        logging.info(f"\n  Strategy: {strategy_name}")
        original_scores = strategy_data['original_scores']
        allocations = strategy_data['allocations']
        
        validated_allocations = {}
        rejected_tickers = []
        
        for ticker, allocation in allocations.items():
            original_score = original_scores.get(ticker, 0)
            current_score = current_scores.get(ticker, 0)
            
            if original_score == 0:
                score_retention = 0
            else:
                score_retention = current_score / original_score
            
            # Check if score retained 85%+ of original value
            if score_retention >= VALIDATION_THRESHOLD:
                validated_allocations[ticker] = allocation
                logging.info(f"    ✓ {ticker}: {score_retention*100:.1f}% retention (orig: {original_score:.2f}, curr: {current_score:.2f})")
            else:
                rejected_tickers.append(ticker)
                logging.warning(f"    ✗ {ticker}: {score_retention*100:.1f}% retention - REJECTED")
        
        # Renormalize allocations after rejections
        if validated_allocations:
            total_weight = sum(validated_allocations.values())
            validated_allocations = {t: w/total_weight for t, w in validated_allocations.items()}
        
        validated_strategies[strategy_name] = {
            'validated_allocations': validated_allocations,
            'rejected_tickers': rejected_tickers,
            'validation_rate': len(validated_allocations) / len(allocations) if allocations else 0
        }
        
        logging.info(f"    Summary: {len(validated_allocations)}/{len(allocations)} picks validated ({validated_strategies[strategy_name]['validation_rate']*100:.1f}%)")
    
    # Select best strategy (same logic as PM)
    logging.info("\n[3/4] Selecting optimal strategy...")
    best_strategy = 'BUY_HOLD'  # Default safe choice
    best_validation_rate = 0
    
    for strategy_name, validation_data in validated_strategies.items():
        if validation_data['validation_rate'] > best_validation_rate:
            best_validation_rate = validation_data['validation_rate']
            best_strategy = strategy_name
    
    logging.info(f"  ✓ Selected: {best_strategy} ({best_validation_rate*100:.1f}% validation rate)")
    
    # Execute trades
    logging.info("\n[4/4] Executing validated trades...")
    client = AlpacaClient()
    account = client.get_account()
    
    if not account:
        logging.error("Could not get account info")
        return False
    
    account_value = float(account['equity'])
    cash = float(account['cash'])
    
    logging.info(f"  Account Value: ${account_value:,.2f}")
    logging.info(f"  Cash Available: ${cash:,.2f}")
    
    # Get current positions
    positions = client.get_positions()
    current_positions = {p['symbol']: float(p['qty']) for p in positions}
    
    # Get current prices
    current_prices = {}
    target_allocations = validated_strategies[best_strategy]['validated_allocations']
    
    for ticker in target_allocations.keys():
        try:
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={POLYGON_API_KEY}"
            res = requests.get(url, timeout=10)
            data = res.json()
            if 'results' in data and len(data['results']) > 0:
                current_prices[ticker] = data['results'][0]['c']
        except Exception as e:
            logging.warning(f"Could not fetch price for {ticker}: {e}")
    
    # Calculate order deltas
    from trading_automation import calculate_position_deltas, execute_orders
    
    deltas = calculate_position_deltas(target_allocations, account_value, current_positions, current_prices)
    
    logging.info(f"\n  Orders to execute: {len(deltas)}")
    for ticker, delta in sorted(deltas.items(), key=lambda x: x[1], reverse=True):
        side = 'BUY' if delta > 0 else 'SELL'
        logging.info(f"    {side} {abs(delta):.2f} shares of {ticker}")
    
    # Execute
    if dry_run:
        logging.info("\n  ⚠️  DRY RUN MODE - No orders placed")
    else:
        execute_orders(client, deltas, dry_run=False)
        logging.info("\n  ✅ Orders executed")
    
    # Archive trade plan
    archive_path = f"archived_trades/pending_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs('archived_trades', exist_ok=True)
    
    # Save validation results to archive
    trade_plan['validation_results'] = {
        'validation_time': datetime.now().isoformat(),
        'selected_strategy': best_strategy,
        'validated_strategies': validated_strategies,
        'orders_executed': deltas,
        'dry_run': dry_run
    }
    
    with open(archive_path, 'w') as f:
        json.dump(trade_plan, f, indent=2)
    
    if os.path.exists(PENDING_TRADES_FILE):
        os.remove(PENDING_TRADES_FILE)
    
    logging.info(f"\n  Trade plan archived: {archive_path}")
    
    logging.info("\n" + "="*80)
    logging.info("✅ VALIDATION & EXECUTION COMPLETE")
    logging.info("="*80)
    
    return True

# ============================================================================
# SCHEDULER DAEMON
# ============================================================================

def run_scheduler_daemon():
    """
    Run as continuous daemon scheduler
    - 8:00 PM ET: Prepare trades for tomorrow
    - 9:00 AM ET: Validate and execute trades
    """
    import time
    from datetime import datetime
    import pytz
    
    logging.info("="*80)
    logging.info("PRE-MARKET PREP SCHEDULER - DAEMON MODE")
    logging.info("="*80)
    logging.info("Schedule:")
    logging.info("  • 8:00 PM ET - Prepare trades for tomorrow")
    logging.info("  • 9:00 AM ET - Validate and execute trades")
    logging.info("")
    
    et_tz = pytz.timezone('America/New_York')
    last_prepare_date = None
    last_execute_date = None
    
    while True:
        try:
            now_et = datetime.now(et_tz)
            current_date = now_et.date()
            current_hour = now_et.hour
            current_minute = now_et.minute
            day_of_week = now_et.weekday()  # 0=Monday, 6=Sunday
            
            # Skip weekends
            if day_of_week >= 5:  # Saturday or Sunday
                time.sleep(3600)  # Sleep 1 hour
                continue
            
            # 8:00 PM - Prepare trades for tomorrow
            if current_hour == 20 and current_minute == 0:
                if last_prepare_date != current_date:
                    logging.info(f"\n🌙 {now_et.strftime('%Y-%m-%d %H:%M')} - Triggering overnight preparation...")
                    try:
                        prepare_next_day_trades()
                        last_prepare_date = current_date
                        logging.info("✅ Preparation complete, sleeping until 9 AM...")
                    except Exception as e:
                        logging.error(f"❌ Preparation failed: {e}")
                    time.sleep(3540)  # Sleep 59 minutes to avoid re-trigger
            
            # 9:00 AM - Validate and execute
            elif current_hour == 9 and current_minute == 0:
                if last_execute_date != current_date:
                    logging.info(f"\n☀️ {now_et.strftime('%Y-%m-%d %H:%M')} - Triggering validation & execution...")
                    try:
                        validate_and_execute_trades(dry_run=False)
                        last_execute_date = current_date
                        logging.info("✅ Execution complete, PM scheduler will take over at 9:15 AM...")
                    except Exception as e:
                        logging.error(f"❌ Execution failed: {e}")
                    time.sleep(3540)  # Sleep 59 minutes to avoid re-trigger
            
            else:
                # Check every minute
                time.sleep(60)
                
        except KeyboardInterrupt:
            logging.info("\n\n🛑 Scheduler stopped by user")
            break
        except Exception as e:
            logging.error(f"❌ Scheduler error: {e}")
            time.sleep(60)

# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description='Pre-Market Preparation System')
    parser.add_argument('--mode', choices=['prepare', 'validate', 'validate-and-execute'],
                       help='Execution mode')
    parser.add_argument('--dry-run', action='store_true',
                       help='Validate only, do not execute orders')
    parser.add_argument('--daemon', action='store_true',
                       help='Run as daemon scheduler (8 PM prepare, 9 AM execute)')
    args = parser.parse_args()
    
    if args.daemon:
        run_scheduler_daemon()
    elif not args.mode:
        parser.error("--mode is required when not using --daemon")
    elif args.mode == 'prepare':
        prepare_next_day_trades()
    elif args.mode == 'validate':
        validate_and_execute_trades(dry_run=True)
    elif args.mode == 'validate-and-execute':
        validate_and_execute_trades(dry_run=args.dry_run)

if __name__ == '__main__':
    main()
