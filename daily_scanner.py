#!/usr/bin/env python3
"""
Daily Market Scanner - Opportunity Identification & Ticker Rotation

Scans an expanded universe of tickers, scores them across multiple factors,
detects sector rotation, and recommends ticker rotations for the 4 strategy groups.

Usage:
    python daily_scanner.py --mode scan
    python daily_scanner.py --mode recommend
    python daily_scanner.py --export rotation_report.json
"""

import os
import argparse
import requests
import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
from event_broadcaster import get_broadcaster
from ticker_downloader import TickerDownloader

# Load environment variables
load_dotenv()

# Initialize event broadcaster
broadcaster = get_broadcaster(source="Market Scanner")

# ============================================================================
# CONFIGURATION
# ============================================================================

# API Keys
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# Load ticker universe from Massive flat-files
## EDIT NOTE: Ensure cache is the fallback not, default ## 
def load_ticker_universe(use_cache: bool = True):
    """
    Load comprehensive ticker universe from Massive flat-files.
    Downloads daily flat-file of 10K+ tickers via S3 API.
    
    Args:
        use_cache: Use cached ticker list if available (< 24 hours old)
    
    Returns:
        List of ticker symbols or None on failure
    """
    try:
        downloader = TickerDownloader()
        
        # Try cache first
        if use_cache:
            tickers = downloader.load_from_cache()
            if tickers:
                logging.info(f"Loaded {len(tickers)} tickers from cache")
                return tickers
        
        # Download fresh from Massive API
        logging.info("Downloading fresh ticker universe from Massive flat-files...")
        tickers = downloader.get_ticker_universe(apply_filters=True)
        
        if tickers:
            # Save to cache for next run
            downloader.save_to_cache(tickers)
            logging.info(f"Loaded {len(tickers)} unique tickers from Massive flat-files")
            return tickers
        else:
            logging.warning("Failed to load ticker universe from Massive")
            return None
            
    except Exception as e:
        logging.warning(f"Could not load ticker universe: {e}")
        logging.info("Falling back to default universe")
        return None

# Load expanded ticker universe from Massive flat-files
TICKER_UNIVERSE = load_ticker_universe()

# Current Holdings (from trading_automation.py)
## EDIT NOTE: remove hardcoded holdings and pull from alpaca instead ## 
CURRENT_HOLDINGS = {
    'CORE': ["GLD", "SLV", "PPLT", "CPER", "SLX", "XLF", "XLB", "XLY", "XLI", "XLK"],
    'SPECULATIVE': ["RKLB", "AA", "MU", "LRCX", "FCX", "HUT", "RIVN", "MSFT", "NVDA", "TSLA"],
    'ASYMMETRIC': ["STLD", "NET", "W", "PANW", "RMBS", "SOFI", "CEG", "OKLO", "QBTS", "IREN"],
    'BENCHMARKS': ["SPY", "QQQ"]
}

# Screening Universe - Use loaded universe or fallback to default
if TICKER_UNIVERSE:
    # Use comprehensive universe from file
    SCREENING_UNIVERSE = {'all_tickers': TICKER_UNIVERSE}
else:
    # Fallback to original expanded universe
    SCREENING_UNIVERSE = {
        'core': [
            # Commodities
            'GLD', 'SLV', 'PALL', 'PPLT', 'CPER', 'DBA', 'DBC', 'UNG', 'USO',
            # Materials/Mining
            'SLX', 'XME', 'PICK', 'COPX', 'FCX', 'AA', 'NUE', 'STLD',
            # Financials
            'JEF', 'GS', 'MS', 'SCHW', 'SF', 'BAC', 'JPM', 'C', 'WFC'
        ],
        
        'speculative': [
            # Semiconductors
            'NVDA', 'AMD', 'AVGO', 'TSM', 'INTC', 'QCOM', 'MU', 'AMAT', 'LRCX',
            # Enterprise SaaS
            'PLTR', 'SNOW', 'NET', 'DDOG', 'CRWD', 'ZS', 'PANW', 'S', 'BILL',
            # EVs & Auto Tech
            'TSLA', 'RIVN', 'LCID', 'NIO', 'XPEV', 'F', 'GM',
            # Mega-cap Tech
            'MSFT', 'GOOGL', 'META', 'AMZN', 'AAPL', 'NFLX', 'CRM', 'ORCL', 'ADBE'
        ],
        
        'asymmetric': [
            # Nuclear/Energy
            'OKLO', 'SMR', 'VST', 'CEG', 'NRG', 'WTRG',
            # Mortgage/Real Estate
            'RMBS', 'UWM', 'RKT', 'PFSI', 'COOP',
            # Quantum Computing
            'QBTS', 'IONQ', 'RGTI', 'ARQQ',
            # Bitcoin Mining & Crypto
            'IREN', 'CLSK', 'RIOT', 'MARA', 'BTBT', 'HUT', 'BITF', 'COIN', 'MSTR',
            # Fintech
            'AFRM', 'UPST', 'SOFI', 'NU', 'HOOD', 'SQ', 'PYPL', 'ALLY',
            # Other Asymmetric
            'RKLB', 'SPCE', 'RDDT', 'ABNB', 'DASH', 'CVNA', 'W'
        ],
        
        'sector_etfs': [
            'XLE',   # Energy
            'XLF',   # Financials
            'XLK',   # Technology
            'XLV',   # Healthcare
            'XLI',   # Industrials
            'XLB',   # Materials
            'XLP',   # Consumer Staples
            'XLY',   # Consumer Discretionary
            'XLRE',  # Real Estate
            'XLU',   # Utilities
            'SPY',   # S&P 500
            'QQQ'    # Nasdaq
        ]
    }

# Scoring Parameters
SCORE_WEIGHTS = {
    'momentum': 0.35,
    'volatility': 0.15,
    'relative_strength': 0.25,
    'breakout': 0.15,
    'volume': 0.10
}

# Rotation Parameters
ROTATION_THRESHOLD = 20.0  # Minimum score difference to trigger rotation

## EDIT NOTE: Are cooldown names recorded somewhere? ## 
COOLDOWN_DAYS = 5  # Days to wait before rotating same ticker again

## EDIT NOTE: Is max rotation by ticker or any portfolio rebalancing activity? Is this stored somewhere ## 
MAX_ROTATIONS_PER_DAY = 2  # Limit rotations to avoid overtrading

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'daily_scanner_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# DATA FETCHING
# ============================================================================

def fetch_price_history(ticker: str, days: int = 365) -> pd.DataFrame:
    """
    Fetch historical price data from Polygon API.
    
    Args:
        ticker: Stock ticker symbol
        days: Number of days to fetch
    
    Returns:
        DataFrame with OHLCV data
    """
    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}?adjusted=true&sort=asc&apiKey={POLYGON_API_KEY}"
        
        data = []
        res = requests.get(url, timeout=10).json()
        
        if res.get('status') == 'ERROR':
            logging.warning(f"  {ticker}: API error - {res.get('error', 'Unknown')}")
            return pd.DataFrame()
        
        data.extend(res.get('results', []))
        
        # Paginate if needed
        while res.get('next_url'):
            res = requests.get(res.get('next_url') + f'&apiKey={POLYGON_API_KEY}', timeout=10).json()
            data.extend(res.get('results', []))
        
        if not data:
            logging.warning(f"  {ticker}: No data returned")
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['ticker'] = ticker
        df['t'] = pd.to_datetime(df['t'], unit='ms')
        df.set_index('t', inplace=True)
        df.sort_index(inplace=True)
        
        return df
        
    except Exception as e:
        logging.error(f"  {ticker}: Error fetching data - {e}")
        return pd.DataFrame()

## EDIT NOTE: Understand the typing of this function ##
def load_universe_data(universe: Dict[str, List[str]]) -> Dict[str, pd.DataFrame]:
    """
    Load historical data for entire screening universe.
    
    Args:
        universe: Dict of ticker lists by category
    
    Returns:
        Dict mapping ticker to DataFrame
    """
    logging.info("Loading screening universe...")
    data = {}
    
    # Flatten universe
    all_tickers = []
    for category, tickers in universe.items():
        all_tickers.extend(tickers)
    
    # Remove duplicates
    all_tickers = list(set(all_tickers))
    logging.info(f"  Total tickers to scan: {len(all_tickers)}")
    
    for i, ticker in enumerate(all_tickers, 1):
        if i % 10 == 0:
            logging.info(f"  Progress: {i}/{len(all_tickers)}")
        
        df = fetch_price_history(ticker)
        if not df.empty and len(df) > 50:  # At least 50 days of data
            data[ticker] = df
    
    logging.info(f"✓ Loaded data for {len(data)}/{len(all_tickers)} tickers")
    broadcaster.broadcast_event(
        "scan",
        f"✓ Data loaded for {len(data)}/{len(all_tickers)} tickers",
        level="INFO"
    )
    return data


# ============================================================================
# SCORING SYSTEM
# ============================================================================

def load_current_positions() -> Dict[str, dict]:
    """
    Load current positions with P&L from dashboard_state.json
    Returns dict of {symbol: {'pnl_pct': float, 'unrealized_pl': float}}
    """
    try:
        state_path = os.path.join(os.path.dirname(__file__), 'dashboard_state.json')
        if not os.path.exists(state_path):
            logging.debug("No dashboard_state.json found - no position penalties will be applied")
            return {}
        
        with open(state_path, 'r') as f:
            state = json.load(f)
        
        positions = {}
        if 'positions' in state:
            for pos in state['positions']:
                symbol = pos['symbol']
                avg_entry = float(pos.get('avg_entry_price', 0))
                current_price = float(pos.get('current_price', 0))
                
                if avg_entry > 0:
                    pnl_pct = (current_price / avg_entry) - 1
                    positions[symbol] = {
                        'pnl_pct': pnl_pct,
                        'unrealized_pl': float(pos.get('unrealized_pl', 0))
                    }
        
        if positions:
            logging.info(f"  Loaded {len(positions)} current positions for loss penalty check")
        
        return positions
    
    except Exception as e:
        logging.debug(f"Could not load positions: {e}")
        return {}

def score_opportunity(ticker: str, df: pd.DataFrame, spy_data: Optional[pd.DataFrame] = None,
                     current_positions: Optional[Dict[str, dict]] = None) -> dict:
    """
    Score ticker across multiple factors.
    
    Args:
        ticker: Stock ticker symbol
        df: Price data for ticker
        spy_data: SPY price data for relative strength calculation
        current_positions: Dict of current positions with P&L (for loss penalty)
    
    Returns:
        Dict with individual and composite scores
    """
    try:
        # Calculate returns
        returns = df['c'].pct_change()
        
        # 1. MOMENTUM SCORE (0-100)
        # Based on 30-day Sharpe and trend strength
        sharpe_30d = (returns.rolling(30).mean() / returns.rolling(30).std()) * np.sqrt(252)
        sharpe_value = sharpe_30d.iloc[-1] if not np.isnan(sharpe_30d.iloc[-1]) else 0
        
        # Trend strength (SMA20/SMA50)
        sma20 = df['c'].rolling(20).mean().iloc[-1]
        sma50 = df['c'].rolling(50).mean().iloc[-1]
        trend_strength = ((sma20 / sma50) - 1) * 100 if sma50 > 0 else 0
        
        momentum_score = min(100, max(0, (sharpe_value * 20) + (trend_strength * 2)))
        
        # 2. VOLATILITY SCORE (0-100)
        # Higher volatility = more asymmetric opportunity
        atr = df['h'] - df['l']
        atr_20d = atr.rolling(20).mean().iloc[-1]
        atr_normalized = (atr_20d / df['c'].iloc[-1]) * 100 if df['c'].iloc[-1] > 0 else 0
        volatility_score = min(100, atr_normalized * 5)
        
        # 3. RELATIVE STRENGTH SCORE (0-100)
        # Performance vs SPY over 30 days
        ticker_return_30d = (df['c'].iloc[-1] / df['c'].iloc[-30] - 1) if len(df) >= 30 else 0
        
        if spy_data is not None and len(spy_data) >= 30:
            spy_return_30d = (spy_data['c'].iloc[-1] / spy_data['c'].iloc[-30] - 1)
            relative_strength = ticker_return_30d - spy_return_30d
        else:
            relative_strength = ticker_return_30d
        
        rs_score = min(100, max(0, 50 + (relative_strength * 200)))
        
        # 4. BREAKOUT SCORE (0-100)
        # Proximity to 52-week high
        high_52w = df['c'].rolling(min(252, len(df))).max().iloc[-1]
        current_price = df['c'].iloc[-1]
        breakout_distance = ((current_price / high_52w) - 1) * 100 if high_52w > 0 else -100
        breakout_score = min(100, max(0, 100 + (breakout_distance * 2)))
        
        # 5. VOLUME SCORE (0-100)
        # Volume surge vs 30-day average
        if 'v' in df.columns:
            avg_volume_30d = df['v'].rolling(30).mean().iloc[-1]
            recent_volume = df['v'].iloc[-1]
            volume_surge = (recent_volume / avg_volume_30d) if avg_volume_30d > 0 else 1.0
            volume_score = min(100, volume_surge * 50)
        else:
            volume_score = 50  # Neutral if no volume data
        
        # 6. RSI (Relative Strength Index) - Overbought/Oversold Filter
        # RSI > 70 = Overbought (reduce score), RSI < 30 = Oversold (opportunity)
        delta = df['c'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.replace(0, 1e-10)  # Avoid division by zero
        rsi = 100 - (100 / (1 + rs))
        rsi_value = rsi.iloc[-1] if not np.isnan(rsi.iloc[-1]) else 50
        
        # RSI adjustment: Penalize overbought, reward oversold
        if rsi_value > 70:
            rsi_multiplier = 1 - ((rsi_value - 70) / 100)  # 0.7x to 1.0x (up to 30% penalty)
        elif rsi_value < 30:
            rsi_multiplier = 1.15  # 15% boost for oversold stocks
        else:
            rsi_multiplier = 1.0  # Neutral range (30-70)
        
        # COMPOSITE SCORE (with RSI adjustment)
        base_composite = (
            momentum_score * SCORE_WEIGHTS['momentum'] +
            volatility_score * SCORE_WEIGHTS['volatility'] +
            rs_score * SCORE_WEIGHTS['relative_strength'] +
            breakout_score * SCORE_WEIGHTS['breakout'] +
            volume_score * SCORE_WEIGHTS['volume']
        )
        
        composite = base_composite * rsi_multiplier
        
        # 7. LOSS PENALTY - Gradual penalty for positions showing losses
        # Prevents system from continuing to hold or rotating back into losers
        # Penalty scales from -1% (10% reduction) to -5%+ (50% reduction cap)
        has_loss_penalty = 0
        loss_penalty_pct = 0
        if current_positions and ticker in current_positions:
            position_pnl = current_positions[ticker]['pnl_pct']
            if position_pnl < -0.01:  # Any loss greater than 1%
                # Gradual scaling: -1% = 10% penalty, -5% = 50% penalty (capped)
                loss_penalty_pct = min(abs(position_pnl) * 10, 0.5)
                composite *= (1 - loss_penalty_pct)
                has_loss_penalty = 1
                logging.info(f"  ⚠️ {ticker} loss penalty: {position_pnl*100:.1f}% P&L → {loss_penalty_pct*100:.0f}% score reduction")
        
        return {
            'ticker': ticker,
            'momentum': round(momentum_score, 2),
            'volatility': round(volatility_score, 2),
            'relative_strength': round(rs_score, 2),
            'breakout': round(breakout_score, 2),
            'volume': round(volume_score, 2),
            'rsi': round(rsi_value, 2),
            'composite': round(composite, 2),
            'price': round(df['c'].iloc[-1], 2),
            'return_30d': round(ticker_return_30d * 100, 2),
            'is_overbought': int(rsi_value > 70),
            'is_oversold': int(rsi_value < 30),
            'has_loss_penalty': has_loss_penalty
        }
        
    except Exception as e:
        logging.error(f"  {ticker}: Scoring error - {e}")
        return {
            'ticker': ticker,
            'momentum': 0, 'volatility': 0, 'relative_strength': 0,
            'breakout': 0, 'volume': 0, 'rsi': 50, 'composite': 0,
            'price': 0, 'return_30d': 0, 'is_overbought': 0, 'is_oversold': 0,
            'has_loss_penalty': 0
        }


def score_all_tickers(data: Dict[str, pd.DataFrame]) -> List[dict]:
    """
    Score all tickers in the universe.
    
    Args:
        data: Dict mapping ticker to DataFrame
    
    Returns:
        List of score dictionaries
    """
    logging.info("Scoring all tickers...")
    
    # Get SPY data for relative strength calculations
    spy_data = data.get('SPY')

    ## EDIT NOTE: What does current positions have to do with loss penalty? ##
    # Load current positions for loss penalty
    current_positions = load_current_positions()
    
    scores = []
    for ticker, df in data.items():
        if len(df) >= 50:  # Need minimum data for scoring
            score = score_opportunity(ticker, df, spy_data, current_positions)
            scores.append(score)
    
    # Sort by composite score
    scores.sort(key=lambda x: x['composite'], reverse=True)
    
    logging.info(f"✓ Scored {len(scores)} tickers")
    return scores


# ============================================================================
# SECTOR ROTATION DETECTION
# ============================================================================

def detect_sector_rotation(data: Dict[str, pd.DataFrame]) -> dict:
    """
    Detect sector rotation trends.
    
    Args:
        data: Market data including sector ETFs
    
    Returns:
        Dict with sector rotation information
    """
    logging.info("Detecting sector rotation...")
    
    sector_etfs = {
        'XLE': 'Energy',
        'XLF': 'Financials',
        'XLK': 'Technology',
        'XLV': 'Healthcare',
        'XLI': 'Industrials',
        'XLB': 'Materials',
        'XLP': 'Consumer Staples',
        'XLY': 'Consumer Discretionary',
        'XLRE': 'Real Estate',
        'XLU': 'Utilities',
    }
    
    # Calculate 30-day returns for each sector
    sector_performance = {}
    for etf, sector in sector_etfs.items():
        if etf in data and len(data[etf]) >= 30:
            returns_30d = (data[etf]['c'].iloc[-1] / data[etf]['c'].iloc[-30] - 1) * 100
            sector_performance[sector] = returns_30d
    
    if not sector_performance:
        logging.warning("No sector ETF data available")
        return {
            'hot_sectors': [],
            'cold_sectors': [],
            'rotation_signal': 'neutral',
            'sector_ranks': []
        }
    
    # Rank sectors
    sorted_sectors = sorted(sector_performance.items(), key=lambda x: x[1], reverse=True)
    hot_sectors = [s[0] for s in sorted_sectors[:3]]
    cold_sectors = [s[0] for s in sorted_sectors[-3:]]
    
    # Rotation signal (defensive vs aggressive)
    defensive_sectors = ['Utilities', 'Consumer Staples', 'Healthcare']
    aggressive_sectors = ['Technology', 'Consumer Discretionary', 'Energy']
    
    defensive_score = sum([sector_performance.get(s, 0) for s in defensive_sectors])
    aggressive_score = sum([sector_performance.get(s, 0) for s in aggressive_sectors])
    
    if aggressive_score > defensive_score * 1.5:
        rotation_signal = 'RISK_ON'
    elif defensive_score > aggressive_score * 1.5:
        rotation_signal = 'RISK_OFF'
    else:
        rotation_signal = 'NEUTRAL'
    
    logging.info(f"  Market regime: {rotation_signal}")
    logging.info(f"  Hot sectors: {', '.join(hot_sectors)}")
    logging.info(f"  Cold sectors: {', '.join(cold_sectors)}")
    
    return {
        'hot_sectors': hot_sectors,
        'cold_sectors': cold_sectors,
        'rotation_signal': rotation_signal,
        'sector_ranks': sorted_sectors
    }


# ============================================================================
# GROUP ASSIGNMENT
# ============================================================================

def assign_to_groups(scores: List[dict], num_per_group: int = 10) -> dict:
    """
    Dynamically assign top-scoring tickers to appropriate groups.
    
    NEW STRATEGY:
    - CORE: ETFs ONLY (high momentum, lower volatility)
    - SPECULATIVE: Individual stocks with good momentum (loosened criteria)
    - ASYMMETRIC: High volatility stocks or breakout potential (loosened criteria)
    - BENCHMARKS: Always SPY/QQQ (static)
    
    Args:
        scores: List of ticker scores
        num_per_group: Target number of tickers per group (default 10)
    
    Returns:
        Dict with group assignments
    """
    logging.info("Assigning tickers to groups...")
    
    # Common ETF tickers (comprehensive list)
    ETF_TICKERS = {
        # Broad Market ETFs
        'SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VOO', 'VEA', 'VWO', 'AGG', 'BND',
        # Sector ETFs
        'XLE', 'XLF', 'XLK', 'XLV', 'XLI', 'XLP', 'XLY', 'XLB', 'XLU', 'XLRE', 'XLC',
        # International ETFs
        'VNQ', 'EFA', 'EEM', 'IEMG', 'VGK', 'VPL', 'INDA', 'FXI', 'EWJ', 'EWZ',
        # Commodity & Metals ETFs
        'GLD', 'SLV', 'USO', 'UNG', 'BOIL', 'KOLD', 'DBC', 'DBA',
        'GDX', 'GDXJ', 'SLX', 'CPER', 'PPLT', 'DBB', 'COPX', 'XME', 'PICK',
        # Bond ETFs
        'TLT', 'IEF', 'SHY', 'LQD', 'HYG', 'EMB', 'JNK', 'MUB', 'BNDX',
        # Thematic & Other ETFs
        'XBI', 'IBB', 'ITB', 'XHB', 'GDXJ', 'SILJ', 'URA', 'REMX', 'LIT'
    }
    
    groups = {
        'CORE': [],
        'SPECULATIVE': [],
        'ASYMMETRIC': [],
        'BENCHMARKS': ['SPY', 'QQQ']
    }
    
    # Separate ETFs and stocks
    etf_scores = [s for s in scores if s['ticker'] in ETF_TICKERS and s['ticker'] not in ['SPY', 'QQQ']]
    stock_scores = [s for s in scores if s['ticker'] not in ETF_TICKERS and s['ticker'] not in ['SPY', 'QQQ']]
    
    # === CORE: ETFs ONLY ===
    # Take top ETFs by composite score
    for score in sorted(etf_scores, key=lambda x: x['composite'], reverse=True):
        if len(groups['CORE']) >= num_per_group:
            break
        ticker = score['ticker']
        groups['CORE'].append(ticker)
        rsi = score.get('rsi', 50)
        rsi_tag = " [OVERBOUGHT]" if score.get('is_overbought', False) else " [OVERSOLD]" if score.get('is_oversold', False) else ""
        logging.info(f"  {ticker} → CORE (ETF, score={score['composite']:.1f}, RSI={rsi:.0f}{rsi_tag})")
    
    # === SPECULATIVE: Stocks with momentum > 50 (LOOSENED from 60) ===
    spec_candidates = [s for s in stock_scores if s['momentum'] > 50]
    for score in sorted(spec_candidates, key=lambda x: x['composite'], reverse=True):
        if len(groups['SPECULATIVE']) >= num_per_group:
            break
        ticker = score['ticker']
        groups['SPECULATIVE'].append(ticker)
        rsi = score.get('rsi', 50)
        rsi_tag = " [OVERBOUGHT]" if score.get('is_overbought', False) else " [OVERSOLD]" if score.get('is_oversold', False) else ""
        logging.info(f"  {ticker} → SPECULATIVE (momentum={score['momentum']:.1f}, RSI={rsi:.0f}{rsi_tag})")
    
    # === ASYMMETRIC: High volatility (>40, LOOSENED from 60) OR breakout (>60, LOOSENED from 70) ===
    asym_candidates = [s for s in stock_scores 
                       if s not in spec_candidates and 
                       (s['volatility'] > 40 or s['breakout'] > 60)]
    for score in sorted(asym_candidates, key=lambda x: x['composite'], reverse=True):
        if len(groups['ASYMMETRIC']) >= num_per_group:
            break
        ticker = score['ticker']
        groups['ASYMMETRIC'].append(ticker)
        rsi = score.get('rsi', 50)
        rsi_tag = " [OVERBOUGHT]" if score.get('is_overbought', False) else " [OVERSOLD]" if score.get('is_oversold', False) else ""
        logging.info(f"  {ticker} → ASYMMETRIC (vol={score['volatility']:.1f}, RSI={rsi:.0f}{rsi_tag})")
    
    # === BACKFILL: Fill remaining slots with best available ===
    remaining_etfs = [s for s in etf_scores if s['ticker'] not in groups['CORE']]
    remaining_stocks = [s for s in stock_scores 
                       if s['ticker'] not in groups['SPECULATIVE'] 
                       and s['ticker'] not in groups['ASYMMETRIC']]
    
    # Fill CORE with remaining ETFs
    for score in sorted(remaining_etfs, key=lambda x: x['composite'], reverse=True):
        if len(groups['CORE']) >= num_per_group:
            break
        groups['CORE'].append(score['ticker'])
        logging.info(f"  {score['ticker']} → CORE (backfill ETF, score={score['composite']:.1f})")
    
    # Fill SPECULATIVE with remaining stocks
    for score in sorted(remaining_stocks, key=lambda x: x['composite'], reverse=True):
        if len(groups['SPECULATIVE']) >= num_per_group:
            break
        groups['SPECULATIVE'].append(score['ticker'])
        logging.info(f"  {score['ticker']} → SPECULATIVE (backfill, score={score['composite']:.1f})")
    
    # Fill ASYMMETRIC with remaining stocks
    for score in sorted(remaining_stocks, key=lambda x: x['composite'], reverse=True):
        if score['ticker'] in groups['SPECULATIVE']:
            continue
        if len(groups['ASYMMETRIC']) >= num_per_group:
            break
        groups['ASYMMETRIC'].append(score['ticker'])
        logging.info(f"  {score['ticker']} → ASYMMETRIC (backfill, score={score['composite']:.1f})")
    
    return groups


# ============================================================================
# PORTFOLIO ANALYTICS
# ============================================================================

def calculate_portfolio_metrics(tickers: List[str], 
                                data: Dict[str, pd.DataFrame],
                                lookback_days: int = 252) -> dict:
    """
    Calculate comprehensive portfolio metrics including Sharpe, volatility, and drawdowns.
    
    Args:
        tickers: List of tickers in portfolio
        data: Market data
        lookback_days: Days to analyze (default 252 = 1 year)
    
    Returns:
        Dict with portfolio metrics
    """
    try:
        # Filter valid tickers with any reasonable amount of data
        valid_tickers = [t for t in tickers if t in data and len(data[t]) >= 60]
        
        if not valid_tickers:
            return {
                'sharpe': 0,
                'annual_return': 0,
                'annual_volatility': 0,
                'max_drawdown': 0,
                'calmar_ratio': 0,
                'win_rate': 0,
                'avg_drawdown': 0,
                'num_drawdowns': 0,
                'recovery_time_avg': 0
            }
        
        # Find common dates (use min of lookback_days and available data)
        min_length = min([len(data[t]) for t in valid_tickers])
        actual_lookback = min(lookback_days, min_length)
        
        common_dates = sorted(set.intersection(*[set(data[t].index[-actual_lookback:]) for t in valid_tickers]))
        
        if len(common_dates) < 20:
            return {'sharpe': 0, 'annual_return': 0, 'annual_volatility': 0, 'max_drawdown': 0,
                    'calmar_ratio': 0, 'win_rate': 0, 'avg_drawdown': 0, 'num_drawdowns': 0, 'recovery_time_avg': 0}
        
        # Calculate equal-weight portfolio returns
        portfolio_values = []
        
        for date in common_dates:
            daily_value = 0
            for ticker in valid_tickers:
                if date in data[ticker].index:
                    daily_value += data[ticker].loc[date, 'c']
            
            # Equal weight
            portfolio_values.append(daily_value / len(valid_tickers))
        
        portfolio_series = pd.Series(portfolio_values, index=common_dates)
        returns = portfolio_series.pct_change().dropna()
        
        # Basic metrics
        annual_return = returns.mean() * 252
        annual_volatility = returns.std() * np.sqrt(252)
        sharpe_ratio = (annual_return / annual_volatility) if annual_volatility > 0 else 0
        
        # Drawdown analysis
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Calmar ratio (return / max drawdown)
        calmar_ratio = (annual_return / abs(max_drawdown)) if max_drawdown != 0 else 0
        
        # Win rate
        win_rate = (returns > 0).sum() / len(returns)
        
        # Drawdown events
        is_drawdown = drawdown < -0.01  # 1% threshold
        drawdown_events = []
        in_drawdown = False
        start_idx = None
        
        for i, (date, dd) in enumerate(drawdown.items()):
            if is_drawdown.iloc[i] and not in_drawdown:
                in_drawdown = True
                start_idx = i
            elif not is_drawdown.iloc[i] and in_drawdown:
                in_drawdown = False
                if start_idx is not None:
                    dd_depth = drawdown.iloc[start_idx:i].min()
                    dd_length = i - start_idx
                    drawdown_events.append({
                        'depth': dd_depth,
                        'length': dd_length
                    })
        
        avg_drawdown = np.mean([e['depth'] for e in drawdown_events]) if drawdown_events else 0
        avg_recovery = np.mean([e['length'] for e in drawdown_events]) if drawdown_events else 0
        
        return {
            'sharpe': round(sharpe_ratio, 3),
            'annual_return': round(annual_return * 100, 2),
            'annual_volatility': round(annual_volatility * 100, 2),
            'max_drawdown': round(max_drawdown * 100, 2),
            'calmar_ratio': round(calmar_ratio, 3),
            'win_rate': round(win_rate * 100, 2),
            'avg_drawdown': round(avg_drawdown * 100, 2),
            'num_drawdowns': len(drawdown_events),
            'recovery_time_avg': round(avg_recovery, 1)
        }
        
    except Exception as e:
        logging.error(f"Error calculating portfolio metrics: {e}")
        return {
            'sharpe': 0,
            'annual_return': 0,
            'annual_volatility': 0,
            'max_drawdown': 0,
            'calmar_ratio': 0,
            'win_rate': 0,
            'avg_drawdown': 0,
            'num_drawdowns': 0,
            'recovery_time_avg': 0
        }


def test_portfolio_sizes(scores: List[dict], 
                        data: Dict[str, pd.DataFrame],
                        sizes: List[int] = [5, 10, 15, 20, 30]) -> List[dict]:
    """
    Test different portfolio sizes and compare metrics.
    
    Args:
        scores: List of ticker scores
        data: Market data
        sizes: Portfolio sizes to test
    
    Returns:
        List of portfolio configurations with metrics
    """
    logging.info("Testing different portfolio sizes...")
    
    results = []
    
    # Remove benchmarks from testing
    test_scores = [s for s in scores if s['ticker'] not in ['SPY', 'QQQ']]
    
    for size in sizes:
        if size > len(test_scores):
            continue
        
        # Select top N by composite score
        top_tickers = [s['ticker'] for s in test_scores[:size]]
        
        # Calculate metrics
        metrics = calculate_portfolio_metrics(top_tickers, data, lookback_days=252)
        
        results.append({
            'size': size,
            'tickers': top_tickers,
            'sharpe': metrics['sharpe'],
            'annual_return': metrics['annual_return'],
            'annual_volatility': metrics['annual_volatility'],
            'max_drawdown': metrics['max_drawdown'],
            'calmar_ratio': metrics['calmar_ratio'],
            'win_rate': metrics['win_rate']
        })
        
        logging.info(f"  Size {size:2d}: Sharpe={metrics['sharpe']:6.3f}, "
                    f"Return={metrics['annual_return']:6.1f}%, Vol={metrics['annual_volatility']:5.1f}%, "
                    f"MaxDD={metrics['max_drawdown']:6.1f}%")
    
    # Find optimal size (best Sharpe)
    if results:
        best = max(results, key=lambda x: x['sharpe'])
        logging.info(f"\n✓ Optimal Portfolio Size: {best['size']} tickers (Sharpe={best['sharpe']:.3f})")
    
    return results


def compare_portfolio_strategies(data: Dict[str, pd.DataFrame],
                                 current_holdings: Dict[str, List[str]],
                                 new_groups: Dict[str, List[str]]) -> dict:
    """
    Compare current holdings vs recommended portfolio with full metrics.
    
    Args:
        data: Market data
        current_holdings: Current ticker groups
        new_groups: Recommended ticker groups
    
    Returns:
        Dict with comparison metrics
    """
    logging.info("Comparing portfolio strategies...")
    
    # Flatten portfolios
    current_portfolio = (
        current_holdings['CORE'] + 
        current_holdings['SPECULATIVE'] + 
        current_holdings['ASYMMETRIC']
    )
    
    new_portfolio = (
        new_groups['CORE'] + 
        new_groups['SPECULATIVE'] + 
        new_groups['ASYMMETRIC']
    )
    
    # Calculate metrics for both
    current_metrics = calculate_portfolio_metrics(current_portfolio, data)
    new_metrics = calculate_portfolio_metrics(new_portfolio, data)
    
    # Calculate improvements
    sharpe_improvement = new_metrics['sharpe'] - current_metrics['sharpe']
    return_improvement = new_metrics['annual_return'] - current_metrics['annual_return']
    vol_change = new_metrics['annual_volatility'] - current_metrics['annual_volatility']
    dd_improvement = current_metrics['max_drawdown'] - new_metrics['max_drawdown']
    
    logging.info("\n  Current Portfolio:")
    logging.info(f"    Sharpe: {current_metrics['sharpe']:.3f}")
    logging.info(f"    Return: {current_metrics['annual_return']:.1f}%")
    logging.info(f"    Volatility: {current_metrics['annual_volatility']:.1f}%")
    logging.info(f"    Max Drawdown: {current_metrics['max_drawdown']:.1f}%")
    logging.info(f"    Calmar: {current_metrics['calmar_ratio']:.3f}")
    logging.info(f"    Win Rate: {current_metrics['win_rate']:.1f}%")
    
    logging.info("\n  Recommended Portfolio:")
    logging.info(f"    Sharpe: {new_metrics['sharpe']:.3f} ({sharpe_improvement:+.3f})")
    logging.info(f"    Return: {new_metrics['annual_return']:.1f}% ({return_improvement:+.1f}%)")
    logging.info(f"    Volatility: {new_metrics['annual_volatility']:.1f}% ({vol_change:+.1f}%)")
    logging.info(f"    Max Drawdown: {new_metrics['max_drawdown']:.1f}% ({dd_improvement:+.1f}% better)")
    logging.info(f"    Calmar: {new_metrics['calmar_ratio']:.3f}")
    logging.info(f"    Win Rate: {new_metrics['win_rate']:.1f}%")
    
    # Recommendation
    if sharpe_improvement > 0.2:
        logging.info("\n  ✓ RECOMMENDATION: ROTATE (Significant Sharpe improvement)")
    elif sharpe_improvement > 0:
        logging.info("\n  ⚠️  RECOMMENDATION: CONSIDER ROTATION (Marginal improvement)")
    else:
        logging.info("\n  ✗ RECOMMENDATION: HOLD (Current portfolio better)")
    
    return {
        'current': current_metrics,
        'recommended': new_metrics,
        'improvements': {
            'sharpe': round(sharpe_improvement, 3),
            'return': round(return_improvement, 2),
            'volatility': round(vol_change, 2),
            'max_drawdown': round(dd_improvement, 2)
        }
    }


# ============================================================================
# ROTATION RECOMMENDATIONS
# ============================================================================

def generate_rotation_recommendations(current_holdings: Dict[str, List[str]],
                                     new_groups: Dict[str, List[str]],
                                     scores: List[dict]) -> List[dict]:
    """
    Generate ticker rotation recommendations with proper one-to-one matching.
    
    Args:
        current_holdings: Current ticker groups
        new_groups: Recommended ticker groups
        scores: List of all ticker scores
    
    Returns:
        List of rotation recommendations
    """
    logging.info("Generating rotation recommendations...")
    
    # Create score lookup
    score_lookup = {s['ticker']: s for s in scores}
    
    recommendations = []
    
    for group_name in ['CORE', 'SPECULATIVE', 'ASYMMETRIC']:
        current_set = set(current_holdings[group_name])
        new_set = set(new_groups[group_name])
        
        # Find tickers to remove and add
        to_remove = current_set - new_set
        to_add = new_set - current_set
        
        # Sort by score (worst to best for removals, best to worst for additions)
        to_remove_sorted = sorted(
            list(to_remove),
            key=lambda t: score_lookup.get(t, {}).get('composite', 0)
        )
        to_add_sorted = sorted(
            list(to_add),
            key=lambda t: score_lookup.get(t, {}).get('composite', 0),
            reverse=True
        )
        
        # Match removals with additions (one-to-one)
        num_rotations = min(len(to_remove_sorted), len(to_add_sorted))
        
        for i in range(num_rotations):
            out_ticker = to_remove_sorted[i]
            in_ticker = to_add_sorted[i]
            
            out_score = score_lookup.get(out_ticker, {}).get('composite', 0)
            in_score = score_lookup.get(in_ticker, {}).get('composite', 0)
            score_delta = in_score - out_score
            
            if score_delta > ROTATION_THRESHOLD:
                recommendations.append({
                    'group': group_name,
                    'action': 'ROTATE',
                    'ticker_out': out_ticker,
                    'ticker_in': in_ticker,
                    'score_out': round(out_score, 2),
                    'score_in': round(in_score, 2),
                    'score_delta': round(score_delta, 2),
                    'reason': f"Score improvement of {score_delta:.1f} points"
                })
                logging.info(f"  {group_name}: {out_ticker} ({out_score:.1f}) → {in_ticker} ({in_score:.1f}) | +{score_delta:.1f}")
    
    if not recommendations:
        logging.info("  No rotations recommended - current holdings optimal")
    else:
        logging.info(f"✓ Generated {len(recommendations)} rotation recommendations")
    
    return recommendations


# ============================================================================
# MAIN SCANNING FUNCTION
# ============================================================================

def daily_scan(export_path: Optional[str] = None) -> dict:
    """
    Perform daily market scan and generate recommendations.
    
    Args:
        export_path: Optional path to export results as JSON
    
    Returns:
        Dict with scan results
    """
    logging.info("="*80)
    logging.info(f"DAILY MARKET SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("="*80)
    
    # Broadcast scan start
    broadcaster.broadcast_event(
        event_type="scan",
        message="🔍 Daily Market Scan Started",
        level="INFO",
        phase="start"
    )
    
    # Broadcast scan start
    ticker_count = len(TICKER_UNIVERSE) if TICKER_UNIVERSE else sum(len(v) for v in SCREENING_UNIVERSE.values())
    broadcaster.broadcast_event(
        "scan",
        f"🔍 Daily market scan initiated - analyzing {ticker_count} tickers",
        level="INFO"
    )
    
    try:
        # 1. Load universe data
        logging.info("\n" + "="*80)
        logging.info("PHASE 1: LOADING UNIVERSE DATA")
        logging.info("="*80)
        broadcaster.broadcast_event(
            event_type="scan",
            message=f"📊 Loading universe data ({ticker_count} tickers)",
            level="INFO",
            phase="loading"
        )
        data = load_universe_data(SCREENING_UNIVERSE)
        
        if not data:
            logging.error("No market data available - aborting")
            return {}
        
        # 2. Score all tickers
        logging.info("\n" + "="*80)
        logging.info("PHASE 2: SCORING TICKERS")
        logging.info("="*80)
        scores = score_all_tickers(data)
        
        # Show top 10
        logging.info("\nTop 10 Tickers by Composite Score:")
        for i, score in enumerate(scores[:10], 1):
            rsi_indicator = "🔴" if score.get('is_overbought', False) else "🟢" if score.get('is_oversold', False) else ""
            logging.info(f"  {i}. {score['ticker']}: {score['composite']:.1f} "
                        f"(M:{score['momentum']:.1f} V:{score['volatility']:.1f} "
                        f"RSI:{score.get('rsi', 50):.0f}{rsi_indicator})")
        
        # Broadcast top opportunities
        top_5 = [f"{s['ticker']} ({s['composite']:.0f})" for s in scores[:5]]
        broadcaster.broadcast_event(
            "scan",
            f"🎯 Scoring complete - Top 5: {', '.join(top_5)}",
            level="INFO"
        )
        
        # 3. Detect sector rotation
        logging.info("\n" + "="*80)
        logging.info("PHASE 3: SECTOR ROTATION ANALYSIS")
        logging.info("="*80)
        rotation_info = detect_sector_rotation(data)
        
        # Broadcast market regime
        regime = rotation_info.get('market_regime', 'UNKNOWN')
        regime_icon = "🟢" if regime == "RISK_ON" else "🔴" if regime == "RISK_OFF" else "🟡"
        hot_sectors = ", ".join(rotation_info.get('hot_sectors', [])[:3])
        broadcaster.broadcast_event(
            "scan",
            f"{regime_icon} Market Regime: {regime} | Hot Sectors: {hot_sectors}",
            level="INFO"
        )
        
        # 4. Assign to groups
        logging.info("\n" + "="*80)
        logging.info("PHASE 4: GROUP ASSIGNMENT")
        logging.info("="*80)
        new_groups = assign_to_groups(scores, num_per_group=10)
        
        # 4A. Test portfolio sizes
        logging.info("\n" + "="*80)
        logging.info("PHASE 4A: PORTFOLIO SIZE TESTING")
        logging.info("="*80)
        size_tests = test_portfolio_sizes(scores, data, sizes=[5, 10, 15, 20, 30])
        
        # 4B. Compare portfolios
        logging.info("\n" + "="*80)
        logging.info("PHASE 4B: PORTFOLIO COMPARISON")
        logging.info("="*80)
        portfolio_comparison = compare_portfolio_strategies(data, CURRENT_HOLDINGS, new_groups)
        
        # 5. Generate recommendations
        logging.info("\n" + "="*80)
        logging.info("PHASE 5: ROTATION RECOMMENDATIONS")
        logging.info("="*80)
        recommendations = generate_rotation_recommendations(
            CURRENT_HOLDINGS,
            new_groups,
            scores
        )
        
        # Broadcast rotation count
        if recommendations:
            broadcaster.broadcast_event(
                "scan",
                f"🔄 {len(recommendations)} rotation opportunities identified - avg score improvement: {np.mean([r['score_delta'] for r in recommendations]):.1f} points",
                level="INFO"
            )
        else:
            broadcaster.broadcast_event(
                "scan",
                "✓ No rotations needed - current portfolio is optimal",
                level="INFO"
            )
        
        # Display portfolio summary
        logging.info("\n" + "="*80)
        logging.info("RECOMMENDED PORTFOLIO COMPOSITION")
        logging.info("="*80)
        
        for group_name in ['CORE', 'SPECULATIVE', 'ASYMMETRIC']:
            current = CURRENT_HOLDINGS[group_name]
            recommended = new_groups[group_name]
            
            logging.info(f"\n{group_name}:")
            logging.info(f"  Current ({len(current)}): {', '.join(current)}")
            logging.info(f"  Recommended ({len(recommended)}): {', '.join(recommended)}")
            
            # Show additions and removals
            added = set(recommended) - set(current)
            removed = set(current) - set(recommended)
            kept = set(current) & set(recommended)
            
            if added:
                logging.info(f"  ➕ ADD: {', '.join(added)}")
            if removed:
                logging.info(f"  ➖ REMOVE: {', '.join(removed)}")
            if kept:
                logging.info(f"  ✓ KEEP: {', '.join(kept)}")
        
        # Compile results
        results = {
            'timestamp': datetime.now().isoformat(),
            'market_regime': rotation_info['rotation_signal'],
            'hot_sectors': rotation_info['hot_sectors'],
            'cold_sectors': rotation_info['cold_sectors'],
            'sector_ranks': rotation_info['sector_ranks'],
            'top_scorers': scores[:20],  # Top 20 tickers
            'current_holdings': CURRENT_HOLDINGS,
            'recommended_groups': new_groups,
            'dynamic_buckets': new_groups,  # For Portfolio Manager compatibility
            'rotation_recommendations': recommendations,
            'portfolio_size_tests': size_tests,
            'portfolio_comparison': portfolio_comparison,
            'total_tickers_scored': len(scores)
        }
        
        # Export if requested
        if export_path:
            with open(export_path, 'w') as f:
                json.dump(results, f, indent=2)
            logging.info(f"\n✓ Results exported to {export_path}")
        
        # Summary
        logging.info("\n" + "="*80)
        logging.info("SCAN SUMMARY")
        logging.info("="*80)
        logging.info(f"Market Regime: {rotation_info['rotation_signal']}")
        logging.info(f"Tickers Scored: {len(scores)}")
        logging.info(f"Rotation Recommendations: {len(recommendations)}")
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
        description='Daily Market Scanner - Opportunity Identification & Ticker Rotation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full daily scan
  python daily_scanner.py --mode scan
  
  # Generate rotation recommendations only
  python daily_scanner.py --mode recommend
  
  # Export results to JSON
  python daily_scanner.py --export rotation_report.json
  
  # Scan with custom rotation threshold
  python daily_scanner.py --mode scan --threshold 25.0
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['scan', 'recommend'],
        default='scan',
        help='Operation mode (default: scan)'
    )
    
    parser.add_argument(
        '--export',
        type=str,
        help='Export results to JSON file'
    )
    
    parser.add_argument(
        '--threshold',
        type=float,
        default=20.0,  # Use literal default value
        help=f'Rotation score threshold (default: 20.0)'
    )
    
    args = parser.parse_args()
    
    # Update threshold if specified
    global ROTATION_THRESHOLD
    if args.threshold != 20.0:
        ROTATION_THRESHOLD = args.threshold
        logging.info(f"Using custom rotation threshold: {ROTATION_THRESHOLD}")
    
    # Run scan
    results = daily_scan(export_path=args.export)
    
    # Print recommendations
    if results and results.get('rotation_recommendations'):
        print("\n" + "="*80)
        print("ROTATION RECOMMENDATIONS")
        print("="*80)
        for rec in results['rotation_recommendations']:
            print(f"\n{rec['group']}:")
            print(f"  OUT: {rec['ticker_out']} (score: {rec['score_out']})")
            print(f"  IN:  {rec['ticker_in']} (score: {rec['score_in']})")
            print(f"  IMPROVEMENT: +{rec['score_delta']} points")
            print(f"  REASON: {rec['reason']}")


if __name__ == '__main__':
    main()
