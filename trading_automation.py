#!/usr/bin/env python3
"""
Trading Automation System - Daily Portfolio Rebalancing

Automates daily rebalancing of a multi-strategy portfolio using Alpaca API.
Selects best performing strategy and executes rebalancing orders.

Usage:
    python trading_automation.py --mode live
    python trading_automation.py --mode dry-run
"""

import os
import argparse
import requests
import pandas as pd
import numpy as np
import time
import logging
from datetime import datetime
from typing import Dict, Tuple, List
from dotenv import load_dotenv
from event_broadcaster import get_broadcaster

# Load environment variables
load_dotenv()

# Initialize event broadcaster
broadcaster = get_broadcaster(source="Trading Automation")

# ============================================================================
# CONFIGURATION
# ============================================================================

# API Keys
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_API_SECRET')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Ticker Groups
CORE_TICKERS = ["GLD", "SLX", "JEF", "CPER"]
BENCHMARKS = ["SPY", "QQQ"]
SPECULATIVE = ["NVDA", "PLTR", "TSLA", "MSFT"]
ASYMMETRIC = ["OKLO", "RMBS", "QBTS", "IREN", "AFRM", "SOFI"]

ALL_TICKERS = CORE_TICKERS + BENCHMARKS + SPECULATIVE + ASYMMETRIC

# Backtest Parameters
CAPITAL = 100000  # Backtest capital (for scaling)
LOOKBACK_DAYS = 10
SHARPE_LOOKBACK = 30
COOLDOWN_DAYS = 5
DRAWDOWN_THRESHOLD = 0.10
PM_MOMENTUM_LOOKBACK = 10

# ============================================================================
# SCANNER INTEGRATION
# ============================================================================

def load_scanner_recommendations(scan_results_path: str = 'scan_results_enhanced.json') -> dict:
    """
    Load ticker recommendations from daily_scanner.py output.
    
    Args:
        scan_results_path: Path to scan results JSON file
    
    Returns:
        Dict with recommended ticker groups or None if file not found
    """
    import json
    import os
    
    if not os.path.exists(scan_results_path):
        logging.warning(f"Scanner results not found: {scan_results_path}")
        return None
    
    try:
        with open(scan_results_path, 'r') as f:
            scan_data = json.load(f)
        
        recommended_groups = scan_data.get('recommended_groups', {})
        portfolio_comparison = scan_data.get('portfolio_comparison', {})
        
        # Log the recommendations
        logging.info("\n" + "="*80)
        logging.info("SCANNER RECOMMENDATIONS LOADED")
        logging.info("="*80)
        
        if portfolio_comparison:
            improvements = portfolio_comparison.get('improvements', {})
            logging.info(f"Expected Sharpe Improvement: {improvements.get('sharpe', 0):+.3f}")
            logging.info(f"Expected Return Improvement: {improvements.get('return', 0):+.1f}%")
            logging.info(f"Expected Volatility Change: {improvements.get('volatility', 0):+.1f}%")
        
        logging.info(f"\nRecommended Portfolio:")
        logging.info(f"  CORE: {', '.join(recommended_groups.get('CORE', []))}")
        logging.info(f"  SPECULATIVE: {', '.join(recommended_groups.get('SPECULATIVE', []))}")
        logging.info(f"  ASYMMETRIC: {', '.join(recommended_groups.get('ASYMMETRIC', []))}")
        logging.info("="*80)
        
        return scan_data
        
    except Exception as e:
        logging.error(f"Error loading scanner results: {e}")
        return None


def apply_scanner_recommendations(scan_data: dict) -> None:
    """
    Apply scanner recommendations to global ticker groups.
    
    Args:
        scan_data: Scanner output data
    """
    global CORE_TICKERS, SPECULATIVE, ASYMMETRIC, ALL_TICKERS
    
    recommended_groups = scan_data.get('recommended_groups', {})
    
    if recommended_groups:
        CORE_TICKERS = recommended_groups.get('CORE', CORE_TICKERS)
        SPECULATIVE = recommended_groups.get('SPECULATIVE', SPECULATIVE)
        ASYMMETRIC = recommended_groups.get('ASYMMETRIC', ASYMMETRIC)
        ALL_TICKERS = CORE_TICKERS + BENCHMARKS + SPECULATIVE + ASYMMETRIC
        
        logging.info("✓ Scanner recommendations applied to ticker groups")
    else:
        logging.warning("No recommended groups found in scanner data")

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'trading_automation_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# DATA FETCHING
# ============================================================================

def fetch_price_history(ticker: str, start_date: str = "2024-01-01") -> pd.DataFrame:
    """
    Fetch historical price data from Polygon API.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Start date in YYYY-MM-DD format
    
    Returns:
        DataFrame with OHLCV data
    """
    data = []
    end_date = datetime.today().strftime("%Y-%m-%d")
    url = f"https://api.massive.com/v2/aggs/ticker/{ticker}/range/1/day/{start_date}/{end_date}?adjusted=true&sort=asc&apiKey={POLYGON_API_KEY}"
    
    res = requests.get(url).json()
    data.extend(res.get('results', []))
    
    # Paginate if needed
    while res.get('next_url'):
        res = requests.get(res.get('next_url') + f'&apiKey={POLYGON_API_KEY}').json()
        data.extend(res.get('results', []))
    
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame()
    
    df['ticker'] = ticker
    df['t'] = pd.to_datetime(df['t'], unit='ms')
    df.set_index('t', inplace=True)
    df.sort_index(inplace=True)
    
    return df


def calculate_indicators(df: pd.DataFrame, lookback: int = 30) -> pd.DataFrame:
    """
    Calculate technical indicators and Sharpe ratio.
    
    Args:
        df: DataFrame with price data
        lookback: Lookback period for Sharpe calculation
    
    Returns:
        DataFrame with added indicators
    """
    df = df.copy()
    df['sma15'] = df['c'].rolling(window=15).mean()
    df['returns'] = df['c'].pct_change()
    df['rolling_mean'] = df['returns'].rolling(window=lookback).mean()
    df['rolling_std'] = df['returns'].rolling(window=lookback).std()
    df['sharpe'] = (df['rolling_mean'] / df['rolling_std']) * np.sqrt(252)
    return df


def load_market_data() -> Dict[str, pd.DataFrame]:
    """
    Load historical data for all tickers.
    
    Returns:
        Dict mapping ticker to DataFrame
    """
    logging.info("Loading market data...")
    data = {}
    
    for ticker in ALL_TICKERS:
        logging.info(f"  Loading {ticker}...")
        df = fetch_price_history(ticker)
        if not df.empty:
            df = calculate_indicators(df, SHARPE_LOOKBACK)
            data[ticker] = df
            logging.info(f"    ✓ Loaded {len(df)} days")
        else:
            logging.warning(f"    ✗ No data for {ticker}")
    
    logging.info(f"✓ Loaded data for {len(data)} tickers")
    return data


def get_fallback_price(ticker: str, data: Dict[str, pd.DataFrame]) -> float:
    """
    Get last available historical price as fallback when current price is unavailable.
    
    Args:
        ticker: Stock ticker symbol
        data: Market data dict
    
    Returns:
        Last closing price from historical data, or 0.0 if unavailable
    """
    if ticker in data and not data[ticker].empty:
        return float(data[ticker]['c'].iloc[-1])
    return 0.0


# ============================================================================
# ALPACA API CLIENT
# ============================================================================

class AlpacaClient:
    """Wrapper for Alpaca API with retry logic and error handling."""
    
    def __init__(self, api_key: str, secret_key: str, base_url: str = ALPACA_BASE_URL):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.data_url = "https://data.alpaca.markets"
        self.headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key
        }
    
    def _retry_api_call(self, func, max_retries: int = 3, delay: int = 2):
        """Retry API calls with exponential backoff."""
        for attempt in range(max_retries):
            try:
                return func()
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                logging.warning(f"API call failed (attempt {attempt+1}/{max_retries}): {e}")
                time.sleep(delay * (2 ** attempt))
    
    def get_account(self) -> dict:
        """Get account information."""
        url = f"{self.base_url}/v2/account"
        response = self._retry_api_call(lambda: requests.get(url, headers=self.headers))
        response.raise_for_status()
        return response.json()
    
    def get_positions(self) -> List[dict]:
        """Get all current positions."""
        url = f"{self.base_url}/v2/positions"
        response = self._retry_api_call(lambda: requests.get(url, headers=self.headers))
        response.raise_for_status()
        return response.json()
    
    def get_clock(self) -> dict:
        """Get market clock status."""
        url = f"{self.base_url}/v2/clock"
        response = self._retry_api_call(lambda: requests.get(url, headers=self.headers))
        response.raise_for_status()
        return response.json()
    
    def cancel_all_orders(self) -> List[dict]:
        """Cancel all open orders."""
        url = f"{self.base_url}/v2/orders"
        response = self._retry_api_call(lambda: requests.delete(url, headers=self.headers))
        response.raise_for_status()
        return response.json()
    
    def get_latest_quote(self, symbol: str) -> dict:
        """Get latest quote for a symbol."""
        url = f"{self.data_url}/v2/stocks/{symbol}/quotes/latest"
        response = self._retry_api_call(lambda: requests.get(url, headers=self.headers))
        response.raise_for_status()
        data = response.json()
        return data.get('quote', data)
    
    def place_order(self, symbol: str, qty: int, side: str, 
                   order_type: str = "market", time_in_force: str = "day") -> dict:
        """
        Place an order.
        
        Args:
            symbol: Ticker symbol
            qty: Number of shares (whole number)
            side: 'buy' or 'sell'
            order_type: 'market' or 'limit'
            time_in_force: 'day', 'gtc', 'opg' (MOO), 'cls' (MOC)
        """
        url = f"{self.base_url}/v2/orders"
        payload = {
            "symbol": symbol,
            "qty": str(int(qty)),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force
        }
        
        response = self._retry_api_call(lambda: requests.post(url, json=payload, headers=self.headers))
        response.raise_for_status()
        return response.json()


# ============================================================================
# STRATEGY SIMULATION (SIMPLIFIED)
# ============================================================================

def run_simple_backtest(data: Dict[str, pd.DataFrame], 
                       ticker_group: List[str],
                       strategy_name: str) -> Tuple[Dict[str, float], float]:
    """
    Run simplified backtest for a ticker group.
    
    Args:
        data: Market data for all tickers
        ticker_group: List of tickers to include
        strategy_name: Name of strategy (for logging)
    
    Returns:
        Tuple of (positions dict, final NAV)
    """
    # Find common dates
    valid_tickers = [t for t in ticker_group if t in data and not data[t].empty]
    if not valid_tickers:
        return {}, CAPITAL
    
    common_dates = sorted(set.intersection(*[set(data[t].index) for t in valid_tickers]))
    if len(common_dates) < LOOKBACK_DAYS + 1:
        return {}, CAPITAL
    
    # Simple equal-weight allocation
    nav = CAPITAL
    cash = CAPITAL
    holdings = {}
    
    for date in common_dates[LOOKBACK_DAYS:]:
        # Calculate Sharpe scores for lookback period
        sharpe_scores = {}
        for ticker in valid_tickers:
            ticker_data = data[ticker]
            if date in ticker_data.index:
                sharpe = ticker_data.loc[date, 'sharpe']
                if not np.isnan(sharpe) and sharpe > 0:
                    sharpe_scores[ticker] = sharpe
        
        # Select top performers
        if sharpe_scores:
            sorted_tickers = sorted(sharpe_scores.items(), key=lambda x: x[1], reverse=True)
            top_tickers = [t[0] for t in sorted_tickers[:min(3, len(sorted_tickers))]]
            
            # Equal weight allocation
            allocation_per_ticker = nav / len(top_tickers)
            holdings = {}
            
            for ticker in top_tickers:
                price = data[ticker].loc[date, 'c']
                shares = allocation_per_ticker / price
                holdings[ticker] = shares
    
    # Calculate final NAV
    latest_date = common_dates[-1]
    nav = 0
    for ticker, shares in holdings.items():
        if ticker in data and latest_date in data[ticker].index:
            price = data[ticker].loc[latest_date, 'c']
            nav += shares * price
    
    return holdings, nav


def select_best_strategy(data: Dict[str, pd.DataFrame]) -> Tuple[str, Dict[str, float], float]:
    """
    Run all strategies and select the best one.
    
    Returns:
        Tuple of (strategy_name, positions, NAV)
    """
    logging.info("Running strategy backtests...")
    
    strategies = {
        'BUY_HOLD': BENCHMARKS,
        'TACTICAL': CORE_TICKERS + BENCHMARKS,
        'SPEC': CORE_TICKERS + BENCHMARKS + SPECULATIVE,
        'ASYM': CORE_TICKERS + BENCHMARKS + SPECULATIVE + ASYMMETRIC
    }
    
    results = {}
    for name, tickers in strategies.items():
        positions, nav = run_simple_backtest(data, tickers, name)
        results[name] = {'positions': positions, 'nav': nav}
        logging.info(f"  {name}: NAV ${nav:,.2f}, {len(positions)} positions")
    
    # Select strategy with highest NAV
    best_strategy = max(results.items(), key=lambda x: x[1]['nav'])
    strategy_name = best_strategy[0]
    positions = best_strategy[1]['positions']
    nav = best_strategy[1]['nav']
    
    logging.info(f"✓ Selected: {strategy_name} (NAV: ${nav:,.2f})")
    
    # Broadcast strategy selection
    broadcaster.broadcast_event(
        event_type="strategy",
        message=f"🎯 Selected strategy: {strategy_name} | NAV: ${nav:,.2f}",
        level="INFO",
        strategy_name=strategy_name,
        nav=nav,
        positions_count=len(positions)
    )
    
    return strategy_name, positions, nav


# ============================================================================
# POSITION DELTA CALCULATION
# ============================================================================

def calculate_position_deltas(target_positions: Dict[str, float],
                              current_positions: Dict[str, float],
                              account_value: float,
                              buying_power: float,
                              current_prices: Dict[str, float],
                              tolerance: float = 0.02) -> Dict[str, dict]:
    """
    Calculate buy/sell deltas to rebalance portfolio.
    
    Args:
        target_positions: dict {ticker: shares} from backtest
        current_positions: dict {ticker: shares} from Alpaca
        account_value: float - total account value
        buying_power: float - available cash
        current_prices: dict {ticker: price}
        tolerance: float - don't trade if delta < tolerance * target
    
    Returns:
        dict: {ticker: {'target': shares, 'current': shares, 'delta': shares, 'action': str}}
    """
    # Scale target positions to actual account value
    scale_factor = account_value / CAPITAL
    scaled_targets = {
        ticker: int(shares * scale_factor)
        for ticker, shares in target_positions.items()
    }
    
    # All tickers
    all_tickers = set(scaled_targets.keys()) | set(current_positions.keys())
    
    deltas = {}
    
    # Calculate deltas
    for ticker in all_tickers:
        target = scaled_targets.get(ticker, 0)
        current = current_positions.get(ticker, 0)
        delta = target - current
        
        # Apply tolerance
        if target > 0 and abs(delta) < target * tolerance:
            action = 'HOLD'
            delta = 0
        elif delta > 0:
            action = 'BUY'
        elif delta < 0:
            action = 'SELL'
        else:
            action = 'HOLD'
        
        deltas[ticker] = {
            'target': target,
            'current': current,
            'delta': delta,
            'action': action
        }
    
    # Validate buying power
    total_buy_cost = sum(
        abs(info['delta']) * current_prices.get(ticker, 0)
        for ticker, info in deltas.items()
        if info['action'] == 'BUY'
    )
    
    if total_buy_cost > buying_power * 0.98:
        logging.warning(f"⚠️  Buy orders (${total_buy_cost:,.0f}) exceed buying power (${buying_power:,.0f})")
        scale_down = (buying_power * 0.98) / total_buy_cost
        logging.warning(f"   Scaling down by {scale_down:.1%}")
        
        for ticker, info in deltas.items():
            if info['action'] == 'BUY':
                original_delta = info['delta']
                scaled_delta = int(original_delta * scale_down)
                if scaled_delta > 0:
                    deltas[ticker]['delta'] = scaled_delta
                    deltas[ticker]['target'] = info['current'] + scaled_delta
                    logging.info(f"   {ticker}: {original_delta} → {scaled_delta} shares")
                else:
                    deltas[ticker]['delta'] = 0
                    deltas[ticker]['action'] = 'HOLD'
                    logging.warning(f"   {ticker}: Insufficient buying power, skipping")
    
    return deltas


# ============================================================================
# ORDER EXECUTION
# ============================================================================

def place_orders(alpaca: AlpacaClient, 
                position_deltas: Dict[str, dict],
                market_is_open: bool,
                dry_run: bool = False) -> dict:
    """
    Place orders (immediate if market open, MOO if closed).
    
    Args:
        alpaca: AlpacaClient instance
        position_deltas: Output from calculate_position_deltas()
        market_is_open: bool - whether market is open
        dry_run: bool - if True, don't actually place orders
    
    Returns:
        dict with execution results
    """
    results = {
        'sell_orders': [],
        'buy_orders': [],
        'errors': []
    }
    
    # Determine order parameters
    if market_is_open:
        order_label = "MARKET"
        time_in_force = 'day'
        timing = "immediately"
    else:
        order_label = "MOO"
        time_in_force = 'opg'
        timing = "at next market open (9:30 AM ET)"
    
    if dry_run:
        logging.info(f"DRY RUN MODE - No orders will be placed")
    
    # Cancel existing orders
    if not dry_run:
        logging.info("Cancelling existing orders...")
        try:
            alpaca.cancel_all_orders()
            logging.info("  ✓ Orders cancelled")
        except Exception as e:
            logging.error(f"  ✗ Error cancelling: {e}")
            results['errors'].append(f"Cancel failed: {e}")
        time.sleep(1)
    
    # SELL orders
    logging.info(f"\n{order_label} SELL Orders:")
    for ticker, info in position_deltas.items():
        if info['action'] == 'SELL':
            qty = abs(int(info['delta']))
            if qty == 0:
                continue
            
            if dry_run:
                logging.info(f"  [DRY RUN] SELL {qty} {ticker}")
                results['sell_orders'].append({'ticker': ticker, 'qty': qty})
            else:
                try:
                    order = alpaca.place_order(ticker, qty, 'sell', time_in_force=time_in_force)
                    logging.info(f"  ✓ SELL {qty} {ticker} - Order ID: {order['id']}")
                    results['sell_orders'].append({'ticker': ticker, 'qty': qty, 'order_id': order['id']})
                    
                    # Broadcast order placement
                    broadcaster.broadcast_event(
                        event_type="order",
                        message=f"📊 SELL {qty} {ticker} ({order_label})",
                        level="INFO",
                        action="SELL",
                        ticker=ticker,
                        quantity=qty,
                        order_type=order_label
                    )
                except Exception as e:
                    logging.error(f"  ✗ Error selling {ticker}: {e}")
                    results['errors'].append(f"SELL {ticker} failed: {e}")
    
    # BUY orders
    logging.info(f"\n{order_label} BUY Orders:")
    for ticker, info in position_deltas.items():
        if info['action'] == 'BUY':
            qty = abs(int(info['delta']))
            if qty == 0:
                continue
            
            if dry_run:
                logging.info(f"  [DRY RUN] BUY {qty} {ticker}")
                results['buy_orders'].append({'ticker': ticker, 'qty': qty})
            else:
                try:
                    order = alpaca.place_order(ticker, qty, 'buy', time_in_force=time_in_force)
                    logging.info(f"  ✓ BUY {qty} {ticker} - Order ID: {order['id']}")
                    results['buy_orders'].append({'ticker': ticker, 'qty': qty, 'order_id': order['id']})
                    
                    # Broadcast order placement
                    broadcaster.broadcast_event(
                        event_type="order",
                        message=f"📊 BUY {qty} {ticker} ({order_label})",
                        level="INFO",
                        action="BUY",
                        ticker=ticker,
                        quantity=qty,
                        order_type=order_label
                    )
                except Exception as e:
                    logging.error(f"  ✗ Error buying {ticker}: {e}")
                    results['errors'].append(f"BUY {ticker} failed: {e}")
    
    results['timing'] = timing
    return results


# ============================================================================
# MAIN REBALANCING FUNCTION
# ============================================================================

def daily_rebalance(dry_run: bool = False, use_scanner: bool = False, scanner_path: str = 'scan_results_enhanced.json'):
    """
    Main function to execute daily portfolio rebalancing.
    
    Args:
        dry_run: If True, simulate without placing actual orders
        use_scanner: If True, load recommendations from daily_scanner.py
        scanner_path: Path to scanner results JSON file
    
    Workflow:
    1. (Optional) Load scanner recommendations
    2. Load market data
    3. Check account status
    4. Select best strategy
    5. Calculate position deltas
    6. Place orders (MOO if after close, immediate if during market hours)
    """
    logging.info("="*80)
    logging.info(f"DAILY REBALANCE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("="*80)
    
    if dry_run:
        logging.info("🔍 DRY RUN MODE - No actual orders will be placed")
    
    try:
        # Load scanner recommendations if requested
        if use_scanner:
            logging.info("\n" + "="*80)
            logging.info("PHASE 0: LOADING SCANNER RECOMMENDATIONS")
            logging.info("="*80)
            scan_data = load_scanner_recommendations(scanner_path)
            
            if scan_data:
                apply_scanner_recommendations(scan_data)
            else:
                logging.warning("Scanner recommendations not available, using default tickers")
        
        # Load market data
        logging.info("\n" + "="*80)
        logging.info("PHASE 1: LOADING MARKET DATA")
        logging.info("="*80)
        data = load_market_data()
        
        if not data:
            logging.error("No market data available - aborting")
            return
        
        # Initialize Alpaca client
        alpaca = AlpacaClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
        
        # Check account status
        logging.info("\n" + "="*80)
        logging.info("PHASE 2: ACCOUNT STATUS")
        logging.info("="*80)
        
        clock = alpaca.get_clock()
        market_is_open = clock['is_open']
        logging.info(f"Market Status: {'OPEN' if market_is_open else 'CLOSED'}")
        if market_is_open:
            logging.info("⚡ Orders will execute immediately")
        else:
            logging.info(f"📅 Next Open: {clock['next_open']}")
        
        account = alpaca.get_account()
        account_value = float(account['equity'])
        cash = float(account['cash'])
        buying_power = float(account['buying_power'])
        
        logging.info(f"Account Value: ${account_value:,.2f}")
        logging.info(f"Cash: ${cash:,.2f}")
        logging.info(f"Buying Power: ${buying_power:,.2f}")
        
        # Select strategy
        logging.info("\n" + "="*80)
        logging.info("PHASE 3: STRATEGY SELECTION")
        logging.info("="*80)
        
        strategy_name, target_positions, target_nav = select_best_strategy(data)
        
        logging.info(f"\nTarget positions ({len(target_positions)} tickers):")
        for ticker, shares in sorted(target_positions.items(), key=lambda x: x[1], reverse=True):
            if shares > 0:
                logging.info(f"  {ticker}: {shares:.2f} shares")
        
        # Get current positions
        logging.info("\n" + "="*80)
        logging.info("PHASE 4: CURRENT POSITIONS")
        logging.info("="*80)
        
        current_positions_raw = alpaca.get_positions()
        current_positions = {pos['symbol']: float(pos['qty']) for pos in current_positions_raw}
        
        if current_positions:
            logging.info(f"Current positions ({len(current_positions)} tickers):")
            for ticker, qty in sorted(current_positions.items(), key=lambda x: x[1], reverse=True):
                logging.info(f"  {ticker}: {qty:.0f} shares")
        else:
            logging.info("No current positions")
        
        # Get current prices
        logging.info("\n" + "="*80)
        logging.info("PHASE 5: FETCHING CURRENT PRICES")
        logging.info("="*80)
        
        all_tickers = set(list(target_positions.keys()) + list(current_positions.keys()))
        current_prices = {}
        
        for ticker in all_tickers:
            try:
                quote = alpaca.get_latest_quote(ticker)
                price = float(quote['ap'])
                
                # Use fallback if price is 0 or unavailable (market closed)
                if price == 0 or price is None:
                    fallback_price = get_fallback_price(ticker, data)
                    if fallback_price > 0:
                        logging.info(f"  {ticker}: ${fallback_price:.2f} (historical - market closed)")
                        current_prices[ticker] = fallback_price
                    else:
                        logging.warning(f"  {ticker}: No price available (skipping)")
                        current_prices[ticker] = 0
                else:
                    logging.info(f"  {ticker}: ${price:.2f}")
                    current_prices[ticker] = price
            except Exception as e:
                # Try fallback on error
                fallback_price = get_fallback_price(ticker, data)
                if fallback_price > 0:
                    logging.info(f"  {ticker}: ${fallback_price:.2f} (historical - API error)")
                    current_prices[ticker] = fallback_price
                else:
                    logging.error(f"  ✗ Error getting price for {ticker}: {e}")
                    current_prices[ticker] = 0
        
        # Calculate deltas
        logging.info("\n" + "="*80)
        logging.info("PHASE 6: POSITION DELTAS")
        logging.info("="*80)
        
        position_deltas = calculate_position_deltas(
            target_positions,
            current_positions,
            account_value,
            buying_power,
            current_prices,
            tolerance=0.02
        )
        
        has_changes = False
        for ticker in sorted(position_deltas.keys()):
            info = position_deltas[ticker]
            if info['action'] != 'HOLD':
                has_changes = True
                logging.info(
                    f"  {ticker}: {info['action']} {abs(int(info['delta']))} shares "
                    f"(current: {int(info['current'])}, target: {int(info['target'])})"
                )
        
        if not has_changes:
            logging.info("✓ No rebalancing needed - portfolio aligned")
            logging.info("\n" + "="*80)
            logging.info("REBALANCE COMPLETE (NO CHANGES)")
            logging.info("="*80)
            return
        
        # Place orders
        logging.info("\n" + "="*80)
        logging.info("PHASE 7: PLACING ORDERS")
        logging.info("="*80)
        
        results = place_orders(alpaca, position_deltas, market_is_open, dry_run)
        
        # Summary
        logging.info("\n" + "="*80)
        logging.info("EXECUTION SUMMARY")
        logging.info("="*80)
        logging.info(f"Sell Orders: {len(results['sell_orders'])}")
        logging.info(f"Buy Orders: {len(results['buy_orders'])}")
        logging.info(f"Errors: {len(results['errors'])}")
        
        if results['errors']:
            logging.error("\nErrors:")
            for error in results['errors']:
                logging.error(f"  {error}")
        
        logging.info("\n" + "="*80)
        if dry_run:
            logging.info("DRY RUN COMPLETE - No actual orders placed")
        elif market_is_open:
            logging.info("REBALANCE COMPLETE - Orders executing now")
        else:
            logging.info("REBALANCE COMPLETE - MOO orders placed")
            logging.info(f"Orders will execute {results['timing']}")
        logging.info("="*80)
        
        return results
        
    except Exception as e:
        logging.error(f"\n{'='*80}")
        logging.error(f"FATAL ERROR: {e}")
        logging.error(f"{'='*80}")
        import traceback
        logging.error(traceback.format_exc())
        raise


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Trading Automation System - Daily Portfolio Rebalancing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run (simulate without placing orders)
  python trading_automation.py --mode dry-run
  
  # Live execution
  python trading_automation.py --mode live
  
  # Test with specific ticker groups
  python trading_automation.py --mode dry-run --tickers GLD,SLX,JEF,CPER
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['live', 'dry-run'],
        default='dry-run',
        help='Execution mode (default: dry-run)'
    )
    
    parser.add_argument(
        '--use-scanner',
        action='store_true',
        help='Load ticker recommendations from daily_scanner.py'
    )
    
    parser.add_argument(
        '--scanner-results',
        type=str,
        default='scan_results_enhanced.json',
        help='Path to scanner results JSON (default: scan_results_enhanced.json)'
    )
    
    parser.add_argument(
        '--tickers',
        type=str,
        help='Override ticker groups (comma-separated)'
    )
    
    args = parser.parse_args()
    
    # Override tickers if specified
    if args.tickers:
        global CORE_TICKERS, ALL_TICKERS
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
        CORE_TICKERS = tickers
        ALL_TICKERS = CORE_TICKERS + BENCHMARKS + SPECULATIVE + ASYMMETRIC
        logging.info(f"Using custom tickers: {tickers}")
    
    # Run rebalance
    dry_run = (args.mode == 'dry-run')
    daily_rebalance(dry_run=dry_run, use_scanner=args.use_scanner, scanner_path=args.scanner_results)


if __name__ == '__main__':
    main()
