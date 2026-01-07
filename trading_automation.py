#!/usr/bin/env python3
"""
Portfolio Manager - Automated Multi-Strategy Trading System
Based on TradingSystem.ipynb with 4 strategies + Portfolio Manager meta-strategy
"""
import os, argparse, requests, pandas as pd, numpy as np, json, time, logging, subprocess, sys
from datetime import datetime, timedelta
from typing import Dict, Tuple, List, Optional
from dotenv import load_dotenv
from event_broadcaster import get_broadcaster

load_dotenv()
broadcaster = get_broadcaster(source="Portfolio Manager")

# API Configuration
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Strategy Parameters (from TradingSystem.ipynb)
LOOKBACK_DAYS = 10              # Rolling window for return comparison
SHARPE_LOOKBACK = 45            # Days for Sharpe ratio calculation (user requested 45)
DRAWDOWN_THRESHOLD = 0.05       # 5% drawdown triggers liquidation (user corrected)
DRAWDOWN_LOOKBACK = 5           # Check drawdown over last 5 days
COOLDOWN_DAYS = 5               # Days to stay in cash after liquidation
PM_MOMENTUM_LOOKBACK = 20       # Portfolio Manager monotonic ranking window
CAPITAL = 100000                # Starting capital for backtests
BACKTEST_DAYS = 180             # Historical period for backtesting
SPEC_MAX_ALLOCATION = 0.15      # Max 15% to speculative bucket
ASYM_CORE_MIN = 0.50            # Min 50% in core
ASYM_SPEC_MAX = 0.40            # Max 40% in speculative
ASYM_ASYM_MAX = 0.30            # Max 30% in asymmetric

# File paths
SCAN_RESULTS_FILE = 'scan_results.json'
STATE_FILE = 'pm_state.json'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ============================================================================
# BUCKET LOADING - Scanner Integration
# ============================================================================

def load_dynamic_buckets_from_scanner():
    """Load dynamic buckets from scanner output - REQUIRED"""
    try:
        with open(SCAN_RESULTS_FILE, 'r') as f:
            scan_data = json.load(f)
        
        if 'dynamic_buckets' not in scan_data:
            raise ValueError("Scanner output missing 'dynamic_buckets' - run daily_scanner.py first")
        
        buckets = scan_data['dynamic_buckets']
        logging.info(f"✓ Loaded dynamic buckets from scanner")
        for bucket, tickers in buckets.items():
            logging.info(f"  {bucket}: {len(tickers)} tickers")
        return buckets
    
    except FileNotFoundError:
        raise FileNotFoundError(f"Scanner results not found at {SCAN_RESULTS_FILE}. Run daily_scanner.py first.")
    except Exception as e:
        raise Exception(f"Failed to load scanner results: {e}")

# ============================================================================
# DATA FETCHING - Polygon API
# ============================================================================

def fetch_price_history(ticker: str, days: int = BACKTEST_DAYS) -> pd.DataFrame:
    """Fetch historical price data from Polygon API"""
    try:
        end_date = datetime.today().strftime("%Y-%m-%d")
        start_date = (datetime.today() - timedelta(days=days+30)).strftime("%Y-%m-%d")  # Extra buffer
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}"
        params = {'adjusted': 'true', 'sort': 'asc', 'apiKey': POLYGON_API_KEY}
        
        data = []
        res = requests.get(url, params=params, timeout=10).json()
        data.extend(res.get('results', []))
        
        # Handle pagination
        while res.get('next_url'):
            res = requests.get(res.get('next_url') + f'&apiKey={POLYGON_API_KEY}', timeout=10).json()
            data.extend(res.get('results', []))
        
        if not data:
            logging.warning(f"No data for {ticker}")
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['ticker'] = ticker
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        df.set_index('t', inplace=True)
        df.sort_index(inplace=True)
        
        return df
    except Exception as e:
        logging.error(f"Error fetching {ticker}: {e}")
        return pd.DataFrame()

def calculate_indicators(df: pd.DataFrame, lookback: int = SHARPE_LOOKBACK) -> pd.DataFrame:
    """Calculate technical indicators (SMA15, Sharpe ratio)"""
    df['sma15'] = df['c'].rolling(window=15).mean()
    df['sma30'] = df['c'].rolling(window=30).mean()
    df['returns'] = df['c'].pct_change()
    df['rolling_mean'] = df['returns'].rolling(window=lookback).mean()
    df['rolling_std'] = df['returns'].rolling(window=lookback).std()
    df['sharpe'] = (df['rolling_mean'] / df['rolling_std']) * np.sqrt(252)
    return df

def load_market_data(buckets: Dict[str, List[str]]) -> Dict[str, pd.DataFrame]:
    """Load historical data for all tickers in buckets"""
    all_tickers = []
    for bucket_tickers in buckets.values():
        all_tickers.extend(bucket_tickers)
    all_tickers = list(set(all_tickers))  # Remove duplicates
    
    logging.info(f"Loading {len(all_tickers)} tickers: {', '.join(all_tickers)}")
    
    data = {}
    for ticker in all_tickers:
        df = fetch_price_history(ticker, BACKTEST_DAYS)
        if not df.empty:
            df = calculate_indicators(df, SHARPE_LOOKBACK)
            data[ticker] = df
            logging.info(f"  ✓ {ticker}: {len(df)} days")
        else:
            logging.warning(f"  ✗ {ticker}: No data")
    
    return data

# ============================================================================
# ALPACA API CLIENT
# ============================================================================

class AlpacaClient:
    def __init__(self):
        self.base_url = ALPACA_BASE_URL
        self.headers = {
            'APCA-API-KEY-ID': ALPACA_API_KEY,
            'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
        }
    
    def get_account(self):
        """Get account information"""
        try:
            res = requests.get(f"{self.base_url}/v2/account", headers=self.headers, timeout=10)
            return res.json()
        except Exception as e:
            logging.error(f"Error getting account: {e}")
            return None
    
    def get_positions(self):
        """Get current positions"""
        try:
            res = requests.get(f"{self.base_url}/v2/positions", headers=self.headers, timeout=10)
            return res.json()
        except Exception as e:
            logging.error(f"Error getting positions: {e}")
            return []
    
    def get_clock(self):
        """Get market clock"""
        try:
            res = requests.get(f"{self.base_url}/v2/clock", headers=self.headers, timeout=10)
            return res.json()
        except Exception as e:
            logging.error(f"Error getting clock: {e}")
            return None
    
    def place_order(self, symbol: str, qty: float, side: str):
        """Place market order"""
        try:
            order = {
                'symbol': symbol,
                'qty': abs(qty),
                'side': side,
                'type': 'market',
                'time_in_force': 'day'
            }
            res = requests.post(f"{self.base_url}/v2/orders", headers=self.headers, json=order, timeout=10)
            return res.json()
        except Exception as e:
            logging.error(f"Error placing order for {symbol}: {e}")
            return None
    
    def liquidate_all_positions(self):
        """Liquidate all positions"""
        try:
            res = requests.delete(f"{self.base_url}/v2/positions", headers=self.headers, timeout=10)
            return res.json()
        except Exception as e:
            logging.error(f"Error liquidating positions: {e}")
            return None

# ============================================================================
# PORTFOLIO ALLOCATION LOGIC
# ============================================================================

def calculate_sharpe_weighted_allocation(tickers: List[str], data: Dict[str, pd.DataFrame], 
                                        date: pd.Timestamp) -> Dict[str, float]:
    """
    Calculate Sharpe-weighted allocation with floor
    Rule: max(sharpe_weight, min(5%, 1/N))
    """
    sharpe_scores = {}
    for ticker in tickers:
        if ticker in data:
            sharpe = data[ticker].loc[date, 'sharpe']
            if pd.notna(sharpe) and sharpe > 0:
                sharpe_scores[ticker] = sharpe
            else:
                sharpe_scores[ticker] = 0.01  # Small positive value
    
    # Normalize to weights
    total_sharpe = sum(sharpe_scores.values())
    if total_sharpe > 0:
        sharpe_weights = {t: s / total_sharpe for t, s in sharpe_scores.items()}
    else:
        sharpe_weights = {t: 1/len(tickers) for t in tickers}
    
    # Apply floor: max(sharpe_weight, min(5%, 1/N))
    min_allocation = min(0.05, 1/len(tickers))
    allocations = {}
    for ticker in tickers:
        allocations[ticker] = max(sharpe_weights[ticker], min_allocation)
    
    # Normalize to sum to 1
    total_alloc = sum(allocations.values())
    allocations = {t: a / total_alloc for t, a in allocations.items()}
    
    return allocations

# ============================================================================
# STRATEGY 1: BUY_HOLD - Buy and Hold Benchmarks
# ============================================================================

def run_buy_hold_backtest(data: Dict[str, pd.DataFrame], common_dates: List[pd.Timestamp],
                          benchmarks: List[str]) -> Tuple[Dict[str, any], float]:
    """
    BUY_HOLD Strategy: Sharpe-weighted BENCHMARKS, buy and hold
    Returns: (nav_history dict, final_nav)
    """
    logging.info("Running BUY_HOLD backtest...")
    
    # Calculate initial allocation (Sharpe-weighted at day 30 for enough history)
    if len(common_dates) <= max(SHARPE_LOOKBACK, 30):
        logging.warning("Not enough dates for BUY_HOLD backtest")
        return {}, CAPITAL
    
    initial_date = common_dates[max(SHARPE_LOOKBACK, 30)]
    allocations = calculate_sharpe_weighted_allocation(benchmarks, data, initial_date)
    
    # Buy shares
    holdings = {}
    for ticker, weight in allocations.items():
        ticker_cash = CAPITAL * weight
        price = data[ticker].loc[common_dates[0], 'c']
        holdings[ticker] = ticker_cash / price
    
    # Track NAV over time
    nav_history = {}
    for date in common_dates:
        total_value = sum(holdings[t] * data[t].loc[date, 'c'] for t in holdings)
        nav_history[date] = total_value
    
    final_nav = nav_history[common_dates[-1]]
    logging.info(f"  BUY_HOLD: ${CAPITAL:,.0f} → ${final_nav:,.0f} ({(final_nav/CAPITAL-1)*100:.2f}%)")
    
    return nav_history, final_nav

# ============================================================================
# STRATEGY 2: TACTICAL - Rotate Between Benchmarks and TICKERS
# ============================================================================

def run_tactical_backtest(data: Dict[str, pd.DataFrame], common_dates: List[pd.Timestamp],
                          benchmarks: List[str], tickers: List[str]) -> Tuple[Dict[str, any], float]:
    """
    TACTICAL Strategy: Rotate between BENCHMARKS and TICKERS based on 10-day returns
    Returns: (nav_history dict, final_nav)
    """
    logging.info("Running TACTICAL backtest...")
    
    if len(common_dates) <= max(SHARPE_LOOKBACK, 30):
        logging.warning("Not enough dates for TACTICAL backtest")
        return {}, CAPITAL
    
    # Start with benchmark allocation
    initial_date = common_dates[max(SHARPE_LOOKBACK, 30)]
    allocations = calculate_sharpe_weighted_allocation(benchmarks, data, initial_date)
    holdings = {}
    for ticker, weight in allocations.items():
        ticker_cash = CAPITAL * weight
        price = data[ticker].loc[common_dates[0], 'c']
        holdings[ticker] = ticker_cash / price
    
    current_strategy = 'BENCHMARK'
    nav_history = {}
    absolute_peak = CAPITAL
    cooldown_until = None
    cash = 0
    
    for i, date in enumerate(common_dates):
        # Calculate portfolio value
        if current_strategy == 'CASH':
            portfolio_value = cash
        else:
            portfolio_value = sum(holdings.get(t, 0) * data[t].loc[date, 'c'] for t in holdings)
        
        nav_history[date] = portfolio_value
        
        # Update peak
        if current_strategy != 'CASH':
            absolute_peak = max(absolute_peak, portfolio_value)
        
        # Check cooldown
        if cooldown_until and date <= cooldown_until:
            continue
        elif cooldown_until and date > cooldown_until:
            # Re-enter with benchmarks
            cooldown_until = None
            holdings = {}
            for benchmark in benchmarks:
                shares = (cash / len(benchmarks)) / data[benchmark].loc[date, 'c']
                holdings[benchmark] = shares
            current_strategy = 'BENCHMARK'
            absolute_peak = cash
            cash = 0
            continue
        
        # Risk management: 5% drawdown check
        if i >= DRAWDOWN_LOOKBACK and portfolio_value > 0:
            recent_navs = [nav_history[common_dates[j]] for j in range(i - DRAWDOWN_LOOKBACK + 1, i + 1)]
            min_recent_nav = min(recent_navs)
            drawdown = (absolute_peak - min_recent_nav) / absolute_peak
            
            if drawdown >= DRAWDOWN_THRESHOLD:
                cash = portfolio_value
                holdings = {}
                current_strategy = 'CASH'
                cooldown_until = common_dates[min(i + COOLDOWN_DAYS, len(common_dates) - 1)]
                logging.info(f"  TACTICAL LIQUIDATION on {date.strftime('%Y-%m-%d')}: DD={drawdown*100:.2f}%")
                continue
        
        # Need enough history for rolling returns
        if i < max(LOOKBACK_DAYS, SHARPE_LOOKBACK):
            continue
        
        # Calculate ETF return (TICKERS)
        etf_price_today = sum(data[t].loc[date, 'c'] for t in tickers) / len(tickers)
        etf_price_lookback = sum(data[t].loc[common_dates[i - LOOKBACK_DAYS], 'c'] for t in tickers) / len(tickers)
        etf_return = (etf_price_today / etf_price_lookback - 1) if etf_price_lookback > 0 else 0
        
        # Calculate BENCHMARK return
        benchmark_price_today = sum(data[t].loc[date, 'c'] for t in benchmarks) / len(benchmarks)
        benchmark_price_lookback = sum(data[t].loc[common_dates[i - LOOKBACK_DAYS], 'c'] for t in benchmarks) / len(benchmarks)
        benchmark_return = (benchmark_price_today / benchmark_price_lookback - 1) if benchmark_price_lookback > 0 else 0
        
        # Determine target strategy
        if etf_return > benchmark_return:
            target_strategy = 'ETF'
            target_tickers = tickers
        else:
            target_strategy = 'BENCHMARK'
            target_tickers = benchmarks
        
        # Rebalance if strategy changed
        if target_strategy != current_strategy:
            current_cash = sum(holdings.get(t, 0) * data[t].loc[date, 'c'] for t in holdings)
            holdings = {}
            
            if target_strategy == 'ETF':
                # Sharpe-weighted allocation
                allocations = calculate_sharpe_weighted_allocation(target_tickers, data, date)
                for ticker, weight in allocations.items():
                    ticker_cash = current_cash * weight
                    holdings[ticker] = ticker_cash / data[ticker].loc[date, 'c']
            else:
                # Equal weight benchmarks
                for ticker in target_tickers:
                    shares = (current_cash / len(target_tickers)) / data[ticker].loc[date, 'c']
                    holdings[ticker] = shares
            
            current_strategy = target_strategy
    
    final_nav = nav_history[common_dates[-1]]
    logging.info(f"  TACTICAL: ${CAPITAL:,.0f} → ${final_nav:,.0f} ({(final_nav/CAPITAL-1)*100:.2f}%)")
    
    return nav_history, final_nav

# ============================================================================
# STRATEGY 3: SPEC - Tactical + 15% Speculative
# ============================================================================

def run_spec_backtest(data: Dict[str, pd.DataFrame], common_dates: List[pd.Timestamp],
                      benchmarks: List[str], tickers: List[str], speculative: List[str]) -> Tuple[Dict[str, any], float]:
    """
    SPEC Strategy: Tactical + 15% Speculative allocation when in ETF mode
    Returns: (nav_history dict, final_nav)
    """
    logging.info("Running SPEC backtest...")
    
    if len(common_dates) <= max(SHARPE_LOOKBACK, 30):
        logging.warning("Not enough dates for SPEC backtest")
        return {}, CAPITAL
    
    # Start with benchmark allocation
    initial_date = common_dates[max(SHARPE_LOOKBACK, 30)]
    allocations = calculate_sharpe_weighted_allocation(benchmarks, data, initial_date)
    holdings = {}
    for ticker, weight in allocations.items():
        ticker_cash = CAPITAL * weight
        price = data[ticker].loc[common_dates[0], 'c']
        holdings[ticker] = ticker_cash / price
    
    current_strategy = 'BENCHMARK'
    nav_history = {}
    absolute_peak = CAPITAL
    cooldown_until = None
    cash = 0
    
    for i, date in enumerate(common_dates):
        # Calculate portfolio value
        if current_strategy == 'CASH':
            portfolio_value = cash
        else:
            portfolio_value = sum(holdings.get(t, 0) * data[t].loc[date, 'c'] for t in holdings if t in data)
        
        nav_history[date] = portfolio_value
        
        # Update peak
        if current_strategy != 'CASH':
            absolute_peak = max(absolute_peak, portfolio_value)
        
        # Check cooldown
        if cooldown_until and date <= cooldown_until:
            continue
        elif cooldown_until and date > cooldown_until:
            cooldown_until = None
            holdings = {}
            for benchmark in benchmarks:
                shares = (cash / len(benchmarks)) / data[benchmark].loc[date, 'c']
                holdings[benchmark] = shares
            current_strategy = 'BENCHMARK'
            absolute_peak = cash
            cash = 0
            continue
        
        # Risk management
        if i >= DRAWDOWN_LOOKBACK and portfolio_value > 0:
            recent_navs = [nav_history[common_dates[j]] for j in range(i - DRAWDOWN_LOOKBACK + 1, i + 1)]
            min_recent_nav = min(recent_navs)
            drawdown = (absolute_peak - min_recent_nav) / absolute_peak
            
            if drawdown >= DRAWDOWN_THRESHOLD:
                cash = portfolio_value
                holdings = {}
                current_strategy = 'CASH'
                cooldown_until = common_dates[min(i + COOLDOWN_DAYS, len(common_dates) - 1)]
                logging.info(f"  SPEC LIQUIDATION on {date.strftime('%Y-%m-%d')}: DD={drawdown*100:.2f}%")
                continue
        
        if i < max(LOOKBACK_DAYS, SHARPE_LOOKBACK):
            continue
        
        # Calculate returns
        etf_price_today = sum(data[t].loc[date, 'c'] for t in tickers) / len(tickers)
        etf_price_lookback = sum(data[t].loc[common_dates[i - LOOKBACK_DAYS], 'c'] for t in tickers) / len(tickers)
        etf_return = (etf_price_today / etf_price_lookback - 1) if etf_price_lookback > 0 else 0
        
        benchmark_price_today = sum(data[t].loc[date, 'c'] for t in benchmarks) / len(benchmarks)
        benchmark_price_lookback = sum(data[t].loc[common_dates[i - LOOKBACK_DAYS], 'c'] for t in benchmarks) / len(benchmarks)
        benchmark_return = (benchmark_price_today / benchmark_price_lookback - 1) if benchmark_price_lookback > 0 else 0
        
        # Determine target strategy
        if etf_return > benchmark_return:
            target_strategy = 'ETF'
            target_tickers = tickers
        else:
            target_strategy = 'BENCHMARK'
            target_tickers = benchmarks
        
        # Rebalance if strategy changed or every 5 days (to update speculative allocation)
        if target_strategy != current_strategy or (target_strategy == 'ETF' and i % 5 == 0):
            current_cash = sum(holdings.get(t, 0) * data[t].loc[date, 'c'] for t in holdings if t in data)
            holdings = {}
            
            if target_strategy == 'ETF':
                # 15% to speculative, 85% to core TICKERS
                speculative_cash = current_cash * SPEC_MAX_ALLOCATION
                core_cash = current_cash - speculative_cash
                
                # Allocate speculative (Sharpe-weighted)
                spec_tickers_with_data = [t for t in speculative if t in data]
                if spec_tickers_with_data:
                    spec_allocs = calculate_sharpe_weighted_allocation(spec_tickers_with_data, data, date)
                    for ticker, weight in spec_allocs.items():
                        ticker_cash = speculative_cash * weight
                        holdings[ticker] = ticker_cash / data[ticker].loc[date, 'c']
                
                # Allocate core (Sharpe-weighted)
                core_allocs = calculate_sharpe_weighted_allocation(target_tickers, data, date)
                for ticker, weight in core_allocs.items():
                    ticker_cash = core_cash * weight
                    holdings[ticker] = holdings.get(ticker, 0) + ticker_cash / data[ticker].loc[date, 'c']
            else:
                # BENCHMARK: equal weight, no speculative
                for ticker in target_tickers:
                    shares = (current_cash / len(target_tickers)) / data[ticker].loc[date, 'c']
                    holdings[ticker] = shares
            
            current_strategy = target_strategy
    
    final_nav = nav_history[common_dates[-1]]
    logging.info(f"  SPEC: ${CAPITAL:,.0f} → ${final_nav:,.0f} ({(final_nav/CAPITAL-1)*100:.2f}%)")
    
    return nav_history, final_nav

# ============================================================================
# STRATEGY 4: ASYM - Tactical + Spec + Asymmetric (3-tier risk-weighted)
# ============================================================================

def run_asym_backtest(data: Dict[str, pd.DataFrame], common_dates: List[pd.Timestamp],
                      benchmarks: List[str], tickers: List[str], speculative: List[str],
                      asymmetric: List[str]) -> Tuple[Dict[str, any], float]:
    """
    ASYM Strategy: 3-tier risk-weighted allocation
    Core (50-100%), Speculative (0-40%), Asymmetric (0-30%)
    Asymmetric only allocated when avg_asym_sharpe > (avg_core + avg_spec)/2 AND > 0.5
    Returns: (nav_history dict, final_nav)
    """
    logging.info("Running ASYM backtest...")
    
    if len(common_dates) <= max(SHARPE_LOOKBACK, 30):
        logging.warning("Not enough dates for ASYM backtest")
        return {}, CAPITAL
    
    # Start with benchmark allocation
    initial_date = common_dates[max(SHARPE_LOOKBACK, 30)]
    allocations = calculate_sharpe_weighted_allocation(benchmarks, data, initial_date)
    holdings = {}
    for ticker, weight in allocations.items():
        ticker_cash = CAPITAL * weight
        price = data[ticker].loc[common_dates[0], 'c']
        holdings[ticker] = ticker_cash / price
    
    current_strategy = 'BENCHMARK'
    nav_history = {}
    absolute_peak = CAPITAL
    cooldown_until = None
    cash = 0
    
    for i, date in enumerate(common_dates):
        # Calculate portfolio value
        if current_strategy == 'CASH':
            portfolio_value = cash
        else:
            portfolio_value = sum(holdings.get(t, 0) * data[t].loc[date, 'c'] for t in holdings if t in data)
        
        nav_history[date] = portfolio_value
        
        # Update peak
        if current_strategy != 'CASH':
            absolute_peak = max(absolute_peak, portfolio_value)
        
        # Check cooldown
        if cooldown_until and date <= cooldown_until:
            continue
        elif cooldown_until and date > cooldown_until:
            cooldown_until = None
            holdings = {}
            for benchmark in benchmarks:
                shares = (cash / len(benchmarks)) / data[benchmark].loc[date, 'c']
                holdings[benchmark] = shares
            current_strategy = 'BENCHMARK'
            absolute_peak = cash
            cash = 0
            continue
        
        # Risk management
        if i >= DRAWDOWN_LOOKBACK and portfolio_value > 0:
            recent_navs = [nav_history[common_dates[j]] for j in range(i - DRAWDOWN_LOOKBACK + 1, i + 1)]
            min_recent_nav = min(recent_navs)
            drawdown = (absolute_peak - min_recent_nav) / absolute_peak
            
            if drawdown >= DRAWDOWN_THRESHOLD:
                cash = portfolio_value
                holdings = {}
                current_strategy = 'CASH'
                cooldown_until = common_dates[min(i + COOLDOWN_DAYS, len(common_dates) - 1)]
                logging.info(f"  ASYM LIQUIDATION on {date.strftime('%Y-%m-%d')}: DD={drawdown*100:.2f}%")
                continue
        
        if i < max(LOOKBACK_DAYS, SHARPE_LOOKBACK):
            continue
        
        # Calculate returns
        etf_price_today = sum(data[t].loc[date, 'c'] for t in tickers) / len(tickers)
        etf_price_lookback = sum(data[t].loc[common_dates[i - LOOKBACK_DAYS], 'c'] for t in tickers) / len(tickers)
        etf_return = (etf_price_today / etf_price_lookback - 1) if etf_price_lookback > 0 else 0
        
        benchmark_price_today = sum(data[t].loc[date, 'c'] for t in benchmarks) / len(benchmarks)
        benchmark_price_lookback = sum(data[t].loc[common_dates[i - LOOKBACK_DAYS], 'c'] for t in benchmarks) / len(benchmarks)
        benchmark_return = (benchmark_price_today / benchmark_price_lookback - 1) if benchmark_price_lookback > 0 else 0
        
        # Determine target strategy
        if etf_return > benchmark_return:
            target_strategy = 'ETF'
            target_tickers = tickers
        else:
            target_strategy = 'BENCHMARK'
            target_tickers = benchmarks
        
        # Rebalance if strategy changed or every 5 days
        if target_strategy != current_strategy or (target_strategy == 'ETF' and i % 5 == 0):
            current_cash = sum(holdings.get(t, 0) * data[t].loc[date, 'c'] for t in holdings if t in data)
            holdings = {}
            
            if target_strategy == 'ETF':
                # === 3-TIER RISK-WEIGHTED ALLOCATION ===
                
                # Calculate average Sharpe for each tier
                core_sharpes = {}
                for ticker in tickers:
                    sharpe = data[ticker].loc[date, 'sharpe']
                    core_sharpes[ticker] = sharpe if pd.notna(sharpe) and sharpe > 0 else 0.01
                
                spec_tickers_with_data = [t for t in speculative if t in data]
                spec_sharpes = {}
                for ticker in spec_tickers_with_data:
                    sharpe = data[ticker].loc[date, 'sharpe']
                    spec_sharpes[ticker] = sharpe if pd.notna(sharpe) and sharpe > 0 else 0.01
                
                asym_tickers_with_data = [t for t in asymmetric if t in data]
                asym_sharpes = {}
                for ticker in asym_tickers_with_data:
                    sharpe = data[ticker].loc[date, 'sharpe']
                    asym_sharpes[ticker] = sharpe if pd.notna(sharpe) and sharpe > 0 else 0.01
                
                avg_core_sharpe = np.mean(list(core_sharpes.values()))
                avg_spec_sharpe = np.mean(list(spec_sharpes.values())) if spec_sharpes else 0.01
                avg_asym_sharpe = np.mean(list(asym_sharpes.values())) if asym_sharpes else 0.01
                
                # Determine tier allocations
                total_sharpe = avg_core_sharpe + avg_spec_sharpe + avg_asym_sharpe
                
                if total_sharpe > 0:
                    raw_core_pct = avg_core_sharpe / total_sharpe
                    raw_spec_pct = avg_spec_sharpe / total_sharpe
                    raw_asym_pct = avg_asym_sharpe / total_sharpe
                    
                    # Asymmetric qualification: avg_asym_sharpe > (avg_core + avg_spec)/2 AND > 0.5
                    asym_threshold = (avg_core_sharpe + avg_spec_sharpe) / 2
                    
                    if avg_asym_sharpe > asym_threshold and avg_asym_sharpe > 0.5:
                        asym_pct = min(raw_asym_pct * 2, ASYM_ASYM_MAX)  # Scale up to 30% max
                    else:
                        asym_pct = 0
                    
                    # Allocate remaining between core and spec
                    remaining = 1.0 - asym_pct
                    spec_pct = min(raw_spec_pct / (raw_core_pct + raw_spec_pct) * remaining, ASYM_SPEC_MAX)
                    core_pct = remaining - spec_pct
                    
                    # Ensure core minimum
                    if core_pct < ASYM_CORE_MIN:
                        shortfall = ASYM_CORE_MIN - core_pct
                        core_pct = ASYM_CORE_MIN
                        if spec_pct >= shortfall:
                            spec_pct -= shortfall
                        else:
                            asym_pct -= (shortfall - spec_pct)
                            spec_pct = 0
                else:
                    core_pct = 1.0
                    spec_pct = 0
                    asym_pct = 0
                
                # Allocate cash to tiers
                core_cash = current_cash * core_pct
                spec_cash = current_cash * spec_pct
                asym_cash = current_cash * asym_pct
                
                # Core allocation
                if core_cash > 0:
                    core_allocs = calculate_sharpe_weighted_allocation(tickers, data, date)
                    for ticker, weight in core_allocs.items():
                        ticker_cash = core_cash * weight
                        holdings[ticker] = ticker_cash / data[ticker].loc[date, 'c']
                
                # Speculative allocation
                if spec_cash > 0 and spec_tickers_with_data:
                    spec_allocs = calculate_sharpe_weighted_allocation(spec_tickers_with_data, data, date)
                    for ticker, weight in spec_allocs.items():
                        ticker_cash = spec_cash * weight
                        holdings[ticker] = ticker_cash / data[ticker].loc[date, 'c']
                
                # Asymmetric allocation
                if asym_cash > 0 and asym_tickers_with_data:
                    asym_allocs = calculate_sharpe_weighted_allocation(asym_tickers_with_data, data, date)
                    for ticker, weight in asym_allocs.items():
                        ticker_cash = asym_cash * weight
                        holdings[ticker] = ticker_cash / data[ticker].loc[date, 'c']
            else:
                # BENCHMARK: equal weight
                for ticker in target_tickers:
                    shares = (current_cash / len(target_tickers)) / data[ticker].loc[date, 'c']
                    holdings[ticker] = shares
            
            current_strategy = target_strategy
    
    final_nav = nav_history[common_dates[-1]]
    logging.info(f"  ASYM: ${CAPITAL:,.0f} → ${final_nav:,.0f} ({(final_nav/CAPITAL-1)*100:.2f}%)")
    
    return nav_history, final_nav

# ============================================================================
# PORTFOLIO MANAGER - Meta-Strategy Selection
# ============================================================================

def count_higher_highs(nav_history: List[float]) -> int:
    """
    Count higher highs (monotonic increases) - measures upward momentum consistency
    """
    count = 0
    for j in range(1, len(nav_history)):
        if nav_history[j] > max(nav_history[:j]):
            count += 1
    return count

def select_best_strategy(strategy_histories: Dict[str, Dict], common_dates: List[pd.Timestamp],
                        current_index: int) -> str:
    """
    Portfolio Manager: Select best strategy using monotonic ranking
    Can return 'CASH' if no strategy shows upward momentum
    """
    if current_index < PM_MOMENTUM_LOOKBACK:
        # Not enough history - pick highest current NAV
        current_navs = {
            name: history[common_dates[current_index]]
            for name, history in strategy_histories.items()
        }
        return max(current_navs.items(), key=lambda x: x[1])[0]
    
    # Get NAV history for lookback period
    momentum_scores = {}
    for name, history in strategy_histories.items():
        nav_history = [history[common_dates[j]] for j in range(current_index - PM_MOMENTUM_LOOKBACK + 1, current_index + 1)]
        momentum_scores[name] = count_higher_highs(nav_history)
    
    # Check if any strategy has positive momentum (at least 1 higher high)
    max_momentum = max(momentum_scores.values())
    if max_momentum == 0:
        logging.info(f"  PM: No upward momentum detected, holding CASH")
        return 'CASH'
    
    # Return strategy with highest momentum
    best_strategy = max(momentum_scores.items(), key=lambda x: x[1])[0]
    return best_strategy

# ============================================================================
# STATE PERSISTENCE - Cooldown Tracking
# ============================================================================

def load_state() -> Dict:
    """Load state from disk"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except:
        return {
            'absolute_peak': None,
            'peak_date': None,
            'cooldown_until': None,
            'last_run': None,
            'last_strategy': None
        }

def save_state(state: Dict):
    """Save state to disk"""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

def check_drawdown(account_value: float, state: Dict) -> Tuple[bool, Dict]:
    """
    Check if 5% drawdown from peak occurred
    Returns: (should_liquidate, updated_state)
    """
    # Check if in cooldown
    if state.get('cooldown_until'):
        cooldown_date = datetime.strptime(state['cooldown_until'], '%Y-%m-%d').date()
        if datetime.now().date() <= cooldown_date:
            logging.info(f"  In cooldown until {state['cooldown_until']}")
            return True, state
    
    # Update peak (initialize if None)
    current_peak = state.get('absolute_peak')
    if current_peak is None:
        current_peak = account_value
        state['absolute_peak'] = account_value
        state['peak_date'] = datetime.now().strftime('%Y-%m-%d')
    
    if account_value > current_peak:
        state['absolute_peak'] = account_value
        state['peak_date'] = datetime.now().strftime('%Y-%m-%d')
    
    # Check drawdown
    drawdown = (state['absolute_peak'] - account_value) / state['absolute_peak']
    
    if drawdown >= DRAWDOWN_THRESHOLD:
        # Trigger liquidation
        state['cooldown_until'] = (datetime.now() + timedelta(days=COOLDOWN_DAYS)).strftime('%Y-%m-%d')
        logging.warning(f"  🚨 DRAWDOWN ALERT: {drawdown*100:.2f}% from peak ${state['absolute_peak']:,.2f}")
        logging.warning(f"  Liquidating and entering cooldown until {state['cooldown_until']}")
        return True, state
    
    return False, state

# ============================================================================
# ORDER EXECUTION
# ============================================================================

def calculate_position_deltas(target_allocations: Dict[str, float], account_value: float,
                              current_positions: Dict[str, float], 
                              current_prices: Dict[str, float]) -> Dict[str, float]:
    """
    Calculate position deltas (buy/sell orders needed)
    target_allocations: {ticker: weight} where weights sum to 1.0
    Returns: {ticker: shares_delta} (positive = buy, negative = sell)
    """
    target_shares = {}
    for ticker, weight in target_allocations.items():
        target_value = account_value * weight
        if ticker in current_prices and current_prices[ticker] > 0:
            target_shares[ticker] = target_value / current_prices[ticker]
        else:
            target_shares[ticker] = 0
    
    # Calculate deltas
    deltas = {}
    for ticker in set(list(target_shares.keys()) + list(current_positions.keys())):
        target = target_shares.get(ticker, 0)
        current = current_positions.get(ticker, 0)
        delta = target - current
        
        if abs(delta) > 0.1:  # Threshold to avoid tiny orders
            deltas[ticker] = delta
    
    return deltas

def execute_orders(client: AlpacaClient, deltas: Dict[str, float], dry_run: bool = True):
    """Execute buy/sell orders"""
    if not deltas:
        logging.info("  No orders to execute")
        return
    
    for ticker, delta in deltas.items():
        side = 'buy' if delta > 0 else 'sell'
        qty = abs(delta)
        
        if dry_run:
            logging.info(f"  [DRY-RUN] {side.upper()} {qty:.2f} shares of {ticker}")
        else:
            logging.info(f"  Placing order: {side.upper()} {qty:.2f} shares of {ticker}")
            result = client.place_order(ticker, qty, side)
            if result:
                logging.info(f"    Order placed: {result.get('id')}")

def start_profit_taker(mode: str = 'moderate'):
    """
    Start intraday profit taker to manage live positions
    Mode options: conservative, moderate, aggressive
    """
    try:
        # Check if profit taker script exists
        profit_taker_path = 'intraday_profit_taker.py'
        if not os.path.exists(profit_taker_path):
            logging.warning(f"Profit taker script not found: {profit_taker_path}")
            return False
        
        # Check if market is open
        client = AlpacaClient()
        clock = client.get_clock()
        if not clock or not clock.get('is_open'):
            logging.info("  Market is closed, skipping profit taker activation")
            return False
        
        logging.info(f"\n{'='*80}")
        logging.info(f"🎯 ACTIVATING INTRADAY PROFIT TAKER ({mode.upper()} mode)")
        logging.info(f"{'='*80}")
        
        # Start profit taker in background
        cmd = [sys.executable, profit_taker_path, '--mode', mode]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        logging.info(f"  ✓ Profit taker started (PID: {process.pid})")
        logging.info(f"  Mode: {mode.upper()}")
        logging.info(f"  Monitoring: All active positions")
        logging.info(f"  Action: Take profits when targets hit")
        logging.info(f"\n  📊 View real-time activity on dashboard: http://localhost:8501")
        logging.info(f"  🛑 To stop: kill {process.pid}\n")
        
        return True
        
    except Exception as e:
        logging.error(f"Error starting profit taker: {e}")
        return False

# ============================================================================
# MAIN EXECUTION FLOW
# ============================================================================

def execute_portfolio_manager(dry_run: bool = True):
    """
    Main Portfolio Manager execution flow
    
    Phases:
    1. Load buckets from scanner (REQUIRED - run daily_scanner.py first)
    2. Load 180 days of historical data
    3. Get Alpaca account status
    4. Check cooldown state
    5. Run all 4 strategy backtests
    6. Check drawdown (liquidate if triggered)
    7. Portfolio Manager selects best strategy
    8. Calculate and execute orders
    """
    
    logging.info("="*80)
    logging.info("PORTFOLIO MANAGER - MULTI-STRATEGY AUTOMATED TRADING")
    logging.info("="*80)
    
    # Phase 1: Load buckets from scanner (REQUIRED)
    logging.info("\n[Phase 1/8] Loading ticker buckets from scanner...")
    buckets = load_dynamic_buckets_from_scanner()
    
    benchmarks = buckets['BENCHMARKS']
    tickers = buckets.get('CORE', buckets.get('TICKERS', []))  # Handle both naming conventions
    speculative = buckets['SPECULATIVE']
    asymmetric = buckets['ASYMMETRIC']
    
    # Phase 2: Load market data
    logging.info("\n[Phase 2/8] Loading historical market data...")
    data = load_market_data(buckets)
    
    if not data:
        logging.error("No data loaded, aborting")
        return
    
    # Find common dates
    date_availability = {ticker: set(df.index) for ticker, df in data.items()}
    common_dates = sorted(set.intersection(*date_availability.values()))
    
    if len(common_dates) < BACKTEST_DAYS:
        logging.warning(f"Only {len(common_dates)} common dates available (need {BACKTEST_DAYS})")
    
    # Filter to last 180 days
    if len(common_dates) > BACKTEST_DAYS:
        backtest_start = common_dates[-1] - timedelta(days=BACKTEST_DAYS)
        common_dates = [d for d in common_dates if d >= backtest_start]
    
    logging.info(f"  Backtest period: {common_dates[0].strftime('%Y-%m-%d')} to {common_dates[-1].strftime('%Y-%m-%d')}")
    logging.info(f"  Trading days: {len(common_dates)}")
    
    # Phase 3: Get account status
    logging.info("\n[Phase 3/8] Getting Alpaca account status...")
    client = AlpacaClient()
    account = client.get_account()
    
    if not account:
        logging.error("Could not get account info")
        return
    
    account_value = float(account['equity'])
    cash = float(account['cash'])
    logging.info(f"  Account Value: ${account_value:,.2f}")
    logging.info(f"  Cash: ${cash:,.2f}")
    
    positions = client.get_positions()
    current_positions = {p['symbol']: float(p['qty']) for p in positions}
    logging.info(f"  Current Positions: {len(current_positions)}")
    
    # Phase 4: Check state and cooldown
    logging.info("\n[Phase 4/8] Checking cooldown state...")
    state = load_state()
    should_liquidate, state = check_drawdown(account_value, state)
    
    if should_liquidate and 'cooldown_until' in state and state['cooldown_until']:
        cooldown_date = datetime.strptime(state['cooldown_until'], '%Y-%m-%d').date()
        if datetime.now().date() <= cooldown_date:
            logging.info("  ⏳ In cooldown period - holding cash, no trades")
            save_state(state)
            return
        else:
            logging.info("  ✓ Cooldown period ended, resuming trading")
            state['cooldown_until'] = None
            state['absolute_peak'] = account_value
    
    # Phase 5: Run all 4 strategy backtests
    logging.info("\n[Phase 5/8] Running strategy backtests...")
    
    bh_history, bh_nav = run_buy_hold_backtest(data, common_dates, benchmarks)
    tactical_history, tactical_nav = run_tactical_backtest(data, common_dates, benchmarks, tickers)
    spec_history, spec_nav = run_spec_backtest(data, common_dates, benchmarks, tickers, speculative)
    asym_history, asym_nav = run_asym_backtest(data, common_dates, benchmarks, tickers, speculative, asymmetric)
    
    strategy_histories = {
        'BUY_HOLD': bh_history,
        'TACTICAL': tactical_history,
        'SPEC': spec_history,
        'ASYM': asym_history
    }
    
    # Phase 6: Check for drawdown (liquidation trigger)
    logging.info("\n[Phase 6/8] Risk management check...")
    if should_liquidate:
        logging.warning("  🚨 Drawdown threshold exceeded - liquidating all positions")
        if not dry_run:
            client.liquidate_all_positions()
        save_state(state)
        return
    
    # Phase 7: Portfolio Manager selection
    logging.info("\n[Phase 7/8] Portfolio Manager strategy selection...")
    selected_strategy = select_best_strategy(strategy_histories, common_dates, len(common_dates) - 1)
    
    logging.info(f"  ✓ Selected Strategy: {selected_strategy}")
    state['last_strategy'] = selected_strategy
    state['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    save_state(state)
    
    if selected_strategy == 'CASH':
        logging.info("  Portfolio Manager recommends holding cash (no upward momentum)")
        if current_positions and not dry_run:
            logging.info("  Liquidating positions to move to cash")
            client.liquidate_all_positions()
        return
    
    # Phase 8: Calculate and execute orders
    logging.info("\n[Phase 8/8] Calculating target allocations...")
    
    # Get current prices
    current_prices = {}
    latest_date = common_dates[-1]
    for ticker in data.keys():
        current_prices[ticker] = data[ticker].loc[latest_date, 'c']
    
    # Determine target allocations based on selected strategy
    if selected_strategy == 'BUY_HOLD':
        target_allocations = calculate_sharpe_weighted_allocation(benchmarks, data, latest_date)
    elif selected_strategy == 'TACTICAL':
        # Use current tactical target (last allocation in backtest)
        # Simplified: use TICKERS if ETF return > benchmark, else benchmarks
        target_allocations = calculate_sharpe_weighted_allocation(tickers, data, latest_date)
    elif selected_strategy == 'SPEC':
        # 85% core, 15% speculative
        core_allocs = calculate_sharpe_weighted_allocation(tickers, data, latest_date)
        spec_tickers_with_data = [t for t in speculative if t in data]
        spec_allocs = calculate_sharpe_weighted_allocation(spec_tickers_with_data, data, latest_date)
        
        target_allocations = {}
        for ticker, weight in core_allocs.items():
            target_allocations[ticker] = weight * 0.85
        for ticker, weight in spec_allocs.items():
            target_allocations[ticker] = weight * 0.15
    else:  # ASYM
        # Use 3-tier allocation (simplified for live trading)
        target_allocations = calculate_sharpe_weighted_allocation(tickers, data, latest_date)
    
    logging.info(f"  Target allocations: {len(target_allocations)} tickers")
    for ticker, weight in sorted(target_allocations.items(), key=lambda x: x[1], reverse=True):
        logging.info(f"    {ticker}: {weight*100:.2f}%")
    
    # Calculate position deltas
    deltas = calculate_position_deltas(target_allocations, account_value, current_positions, current_prices)
    
    logging.info(f"\n  Orders to execute: {len(deltas)}")
    
    # Execute orders
    execute_orders(client, deltas, dry_run=dry_run)
    
    logging.info("\n" + "="*80)
    logging.info("Portfolio Manager execution complete")
    logging.info("="*80)

def main():
    parser = argparse.ArgumentParser(description='Portfolio Manager - Multi-Strategy Automated Trading')
    parser.add_argument('--mode', choices=['live', 'dry-run'], default='dry-run',
                       help='Execution mode (default: dry-run)')
    parser.add_argument('--start-profit-taker', action='store_true',
                       help='Automatically start intraday profit taker after order execution (live mode only)')
    parser.add_argument('--profit-taker-mode', choices=['conservative', 'moderate', 'aggressive'],
                       default='moderate', help='Profit taker mode (default: moderate)')
    args = parser.parse_args()
    
    dry_run = (args.mode == 'dry-run')
    
    try:
        execute_portfolio_manager(dry_run=dry_run)
        
        # Start profit taker if requested and in live mode
        if args.start_profit_taker and not dry_run:
            start_profit_taker(mode=args.profit_taker_mode)
        elif args.start_profit_taker and dry_run:
            logging.info("\n⚠️  Profit taker not started (dry-run mode)")
            logging.info("   Use --mode live to activate profit taker\n")
            
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)

if __name__ == '__main__':
    main()
