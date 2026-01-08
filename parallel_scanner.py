#!/usr/bin/env python3
"""
Parallel Market Scanner - High-Performance Ticker Analysis

Optimized for processing 10K+ tickers using async I/O and multiprocessing.
Downloads ticker universe from Massive flat-files and processes in parallel batches.

Key Features:
- Async HTTP requests for concurrent API calls
- Multiprocessing for CPU-bound calculations
- Smart batching to avoid API rate limits
- Progress tracking and error recovery

Usage:
    python parallel_scanner.py --mode scan
    python parallel_scanner.py --export scan_results.json --workers 8
"""

import os
import asyncio
import aiohttp
import requests
import pandas as pd
import numpy as np
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import partial
from dotenv import load_dotenv
from event_broadcaster import get_broadcaster
from ticker_downloader import TickerDownloader

# Load environment variables
load_dotenv()

# Initialize event broadcaster
broadcaster = get_broadcaster(source="Parallel Scanner")

# ============================================================================
# CONFIGURATION
# ============================================================================

# API Keys
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')

# Parallel Processing
DEFAULT_WORKERS = 8  # CPU cores for multiprocessing
BATCH_SIZE = 50      # API requests per batch
MAX_CONCURRENT = 10  # Max concurrent HTTP connections
REQUEST_DELAY = 0.1  # Delay between requests (seconds)

# Scoring Parameters (same as original scanner)
SCORE_WEIGHTS = {
    'momentum': 0.35,
    'volatility': 0.15,
    'relative_strength': 0.25,
    'breakout': 0.15,
    'volume': 0.10
}

# Quality Filters
MIN_PRICE = 1.0
MIN_VOLUME = 100000
MIN_DATA_POINTS = 50

# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'parallel_scanner_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# ASYNC DATA FETCHING
# ============================================================================

async def fetch_price_history_async(
    session: aiohttp.ClientSession,
    ticker: str,
    days: int = 365,
    semaphore: asyncio.Semaphore = None
) -> Tuple[str, pd.DataFrame]:
    """
    Async fetch historical price data from Polygon API.
    
    Args:
        session: aiohttp session
        ticker: Stock ticker symbol
        days: Number of days to fetch
        semaphore: Semaphore for rate limiting
    
    Returns:
        Tuple of (ticker, DataFrame)
    """
    if semaphore:
        async with semaphore:
            return await _fetch_data(session, ticker, days)
    else:
        return await _fetch_data(session, ticker, days)


async def _fetch_data(session: aiohttp.ClientSession, ticker: str, days: int) -> Tuple[str, pd.DataFrame]:
    """Internal fetch function"""
    try:
        end_date = datetime.today()
        start_date = end_date - timedelta(days=days)
        
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/day/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}?adjusted=true&sort=asc&apiKey={POLYGON_API_KEY}"
        
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
            res = await response.json()
            
            if res.get('status') == 'ERROR':
                logging.debug(f"  {ticker}: API error - {res.get('error', 'Unknown')}")
                return (ticker, pd.DataFrame())
            
            data = res.get('results', [])
            
            if not data:
                logging.debug(f"  {ticker}: No data returned")
                return (ticker, pd.DataFrame())
            
            df = pd.DataFrame(data)
            df['ticker'] = ticker
            df['t'] = pd.to_datetime(df['t'], unit='ms')
            df.set_index('t', inplace=True)
            df.sort_index(inplace=True)
            
            # Apply quality filters
            if len(df) < MIN_DATA_POINTS:
                return (ticker, pd.DataFrame())
            
            latest_price = df['c'].iloc[-1]
            if latest_price < MIN_PRICE:
                return (ticker, pd.DataFrame())
            
            if 'v' in df.columns:
                avg_volume = df['v'].mean()
                if avg_volume < MIN_VOLUME:
                    return (ticker, pd.DataFrame())
            
            return (ticker, df)
            
    except asyncio.TimeoutError:
        logging.debug(f"  {ticker}: Request timeout")
        return (ticker, pd.DataFrame())
    except Exception as e:
        logging.debug(f"  {ticker}: Error - {e}")
        return (ticker, pd.DataFrame())


async def load_universe_data_async(tickers: List[str], max_concurrent: int = MAX_CONCURRENT) -> Dict[str, pd.DataFrame]:
    """
    Load historical data for ticker universe using async I/O.
    
    Args:
        tickers: List of ticker symbols
        max_concurrent: Max concurrent HTTP connections
    
    Returns:
        Dict mapping ticker to DataFrame
    """
    logging.info(f"Loading data for {len(tickers)} tickers (async)...")
    broadcaster.broadcast_event(
        "scan",
        f"📊 Loading data for {len(tickers)} tickers (parallel mode)",
        level="INFO"
    )
    
    data = {}
    semaphore = asyncio.Semaphore(max_concurrent)
    
    # Process in batches to show progress
    batch_size = BATCH_SIZE
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    
    async with aiohttp.ClientSession() as session:
        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(tickers))
            batch_tickers = tickers[start_idx:end_idx]
            
            # Create tasks for batch
            tasks = [
                fetch_price_history_async(session, ticker, semaphore=semaphore)
                for ticker in batch_tickers
            ]
            
            # Execute batch
            results = await asyncio.gather(*tasks)
            
            # Store results
            for ticker, df in results:
                if not df.empty:
                    data[ticker] = df
            
            # Progress update
            progress = (batch_idx + 1) / total_batches * 100
            logging.info(f"  Progress: {batch_idx + 1}/{total_batches} batches ({progress:.1f}%) - {len(data)} tickers loaded")
            
            # Small delay between batches
            if batch_idx < total_batches - 1:
                await asyncio.sleep(REQUEST_DELAY)
    
    logging.info(f"✓ Loaded data for {len(data)}/{len(tickers)} tickers")
    broadcaster.broadcast_event(
        "scan",
        f"✓ Data loaded: {len(data)}/{len(tickers)} tickers passed quality filters",
        level="INFO"
    )
    
    return data


# ============================================================================
# PARALLEL SCORING
# ============================================================================

def score_ticker_worker(ticker: str, df_dict: dict, spy_dict: dict = None) -> dict:
    """
    Worker function to score a single ticker (CPU-bound).
    
    Args:
        ticker: Stock ticker symbol
        df_dict: Dict representation of price DataFrame
        spy_dict: Dict representation of SPY DataFrame
    
    Returns:
        Dict with scores
    """
    try:
        # Reconstruct DataFrame from dict
        df = pd.DataFrame(df_dict)
        df.index = pd.to_datetime(df.index)
        
        spy_data = None
        if spy_dict:
            spy_data = pd.DataFrame(spy_dict)
            spy_data.index = pd.to_datetime(spy_data.index)
        
        # Calculate returns
        returns = df['c'].pct_change()
        
        # 1. MOMENTUM SCORE (0-100)
        sharpe_30d = (returns.rolling(30).mean() / returns.rolling(30).std()) * np.sqrt(252)
        sharpe_value = sharpe_30d.iloc[-1] if not np.isnan(sharpe_30d.iloc[-1]) else 0
        
        sma20 = df['c'].rolling(20).mean().iloc[-1]
        sma50 = df['c'].rolling(50).mean().iloc[-1]
        trend_strength = ((sma20 / sma50) - 1) * 100 if sma50 > 0 else 0
        
        momentum_score = min(100, max(0, (sharpe_value * 20) + (trend_strength * 2)))
        
        # 2. VOLATILITY SCORE (0-100)
        atr = df['h'] - df['l']
        atr_20d = atr.rolling(20).mean().iloc[-1]
        atr_normalized = (atr_20d / df['c'].iloc[-1]) * 100 if df['c'].iloc[-1] > 0 else 0
        volatility_score = min(100, atr_normalized * 5)
        
        # 3. RELATIVE STRENGTH SCORE (0-100)
        ticker_return_30d = (df['c'].iloc[-1] / df['c'].iloc[-30] - 1) if len(df) >= 30 else 0
        
        if spy_data is not None and len(spy_data) >= 30:
            spy_return_30d = (spy_data['c'].iloc[-1] / spy_data['c'].iloc[-30] - 1)
            relative_strength = ticker_return_30d - spy_return_30d
        else:
            relative_strength = ticker_return_30d
        
        rs_score = min(100, max(0, 50 + (relative_strength * 200)))
        
        # 4. BREAKOUT SCORE (0-100)
        high_52w = df['c'].rolling(min(252, len(df))).max().iloc[-1]
        current_price = df['c'].iloc[-1]
        breakout_distance = ((current_price / high_52w) - 1) * 100 if high_52w > 0 else -100
        breakout_score = min(100, max(0, 100 + (breakout_distance * 2)))
        
        # 5. VOLUME SCORE (0-100)
        if 'v' in df.columns:
            avg_volume_30d = df['v'].rolling(30).mean().iloc[-1]
            recent_volume = df['v'].iloc[-1]
            volume_surge = (recent_volume / avg_volume_30d) if avg_volume_30d > 0 else 1.0
            volume_score = min(100, volume_surge * 50)
        else:
            volume_score = 50
        
        # COMPOSITE SCORE
        composite = (
            momentum_score * SCORE_WEIGHTS['momentum'] +
            volatility_score * SCORE_WEIGHTS['volatility'] +
            rs_score * SCORE_WEIGHTS['relative_strength'] +
            breakout_score * SCORE_WEIGHTS['breakout'] +
            volume_score * SCORE_WEIGHTS['volume']
        )
        
        return {
            'ticker': ticker,
            'momentum': round(momentum_score, 2),
            'volatility': round(volatility_score, 2),
            'relative_strength': round(rs_score, 2),
            'breakout': round(breakout_score, 2),
            'volume': round(volume_score, 2),
            'composite': round(composite, 2),
            'price': round(df['c'].iloc[-1], 2),
            'return_30d': round(ticker_return_30d * 100, 2)
        }
        
    except Exception as e:
        logging.debug(f"  {ticker}: Scoring error - {e}")
        return {
            'ticker': ticker,
            'momentum': 0, 'volatility': 0, 'relative_strength': 0,
            'breakout': 0, 'volume': 0, 'composite': 0,
            'price': 0, 'return_30d': 0
        }


def score_all_tickers_parallel(data: Dict[str, pd.DataFrame], workers: int = DEFAULT_WORKERS) -> List[dict]:
    """
    Score all tickers using multiprocessing.
    
    Args:
        data: Dict mapping ticker to DataFrame
        workers: Number of worker processes
    
    Returns:
        List of score dictionaries
    """
    logging.info(f"Scoring {len(data)} tickers (parallel, {workers} workers)...")
    broadcaster.broadcast_event(
        "scan",
        f"🎯 Scoring {len(data)} tickers with {workers} workers",
        level="INFO"
    )
    
    # Get SPY data
    spy_dict = None
    if 'SPY' in data:
        spy_df = data['SPY']
        spy_dict = {
            'c': spy_df['c'].to_dict(),
            'index': spy_df.index.astype(str).tolist()
        }
    
    # Prepare data for workers (convert DataFrames to dicts)
    ticker_data = []
    for ticker, df in data.items():
        df_dict = {
            'c': df['c'].to_dict(),
            'h': df['h'].to_dict(),
            'l': df['l'].to_dict(),
            'v': df.get('v', pd.Series()).to_dict(),
            'index': df.index.astype(str).tolist()
        }
        ticker_data.append((ticker, df_dict, spy_dict))
    
    # Process in parallel
    scores = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(score_ticker_worker, ticker, df_dict, spy_dict): ticker
            for ticker, df_dict, spy_dict in ticker_data
        }
        
        completed = 0
        total = len(futures)
        
        for future in as_completed(futures):
            completed += 1
            if completed % 100 == 0 or completed == total:
                progress = completed / total * 100
                logging.info(f"  Progress: {completed}/{total} ({progress:.1f}%)")
            
            try:
                score = future.result()
                if score['composite'] > 0:  # Only keep valid scores
                    scores.append(score)
            except Exception as e:
                ticker = futures[future]
                logging.error(f"  {ticker}: Worker error - {e}")
    
    # Sort by composite score
    scores.sort(key=lambda x: x['composite'], reverse=True)
    
    logging.info(f"✓ Scored {len(scores)} tickers")
    broadcaster.broadcast_event(
        "scan",
        f"✓ Scoring complete: {len(scores)} tickers ranked",
        level="INFO"
    )
    
    return scores


# ============================================================================
# MAIN SCAN FUNCTION
# ============================================================================

async def parallel_scan(
    export_path: Optional[str] = None,
    workers: int = DEFAULT_WORKERS,
    use_cache: bool = True
) -> dict:
    """
    Perform parallel market scan.
    
    Args:
        export_path: Optional path to export results
        workers: Number of worker processes for scoring
        use_cache: Use cached ticker list if available
    
    Returns:
        Dict with scan results
    """
    logging.info("="*80)
    logging.info(f"PARALLEL MARKET SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("="*80)
    
    broadcaster.broadcast_event(
        "scan",
        "🚀 Parallel Market Scan Started",
        level="INFO"
    )
    
    try:
        # 1. Download ticker universe from Massive
        logging.info("\n" + "="*80)
        logging.info("PHASE 1: DOWNLOADING TICKER UNIVERSE")
        logging.info("="*80)
        
        downloader = TickerDownloader()
        
        # Try to load from cache first
        if use_cache:
            tickers = downloader.load_from_cache()
            if tickers:
                logging.info(f"Using cached ticker list: {len(tickers)} tickers")
        
        # Download fresh if no cache
        if not tickers:
            tickers = downloader.get_ticker_universe(apply_filters=True)
            if tickers:
                downloader.save_to_cache(tickers)
        
        if not tickers:
            logging.error("Failed to load ticker universe")
            return {}
        
        logging.info(f"✓ Ticker universe ready: {len(tickers)} tickers")
        broadcaster.broadcast_event(
            "scan",
            f"✓ Ticker universe loaded: {len(tickers)} tickers",
            level="INFO"
        )
        
        # 2. Load market data (async)
        logging.info("\n" + "="*80)
        logging.info("PHASE 2: LOADING MARKET DATA (ASYNC)")
        logging.info("="*80)
        
        data = await load_universe_data_async(tickers, max_concurrent=MAX_CONCURRENT)
        
        if not data:
            logging.error("No market data available - aborting")
            return {}
        
        # 3. Score tickers (parallel)
        logging.info("\n" + "="*80)
        logging.info("PHASE 3: SCORING TICKERS (PARALLEL)")
        logging.info("="*80)
        
        scores = score_all_tickers_parallel(data, workers=workers)
        
        # Show top 20
        logging.info("\nTop 20 Tickers by Composite Score:")
        for i, score in enumerate(scores[:20], 1):
            logging.info(f"  {i:2d}. {score['ticker']:6s}: {score['composite']:6.1f} "
                        f"(M:{score['momentum']:5.1f} V:{score['volatility']:5.1f} "
                        f"RS:{score['relative_strength']:5.1f} B:{score['breakout']:5.1f})")
        
        # Broadcast top opportunities
        top_10 = [f"{s['ticker']} ({s['composite']:.0f})" for s in scores[:10]]
        broadcaster.broadcast_event(
            "scan",
            f"🎯 Top 10: {', '.join(top_10)}",
            level="INFO"
        )
        
        # 4. Prepare results
        results = {
            'timestamp': datetime.now().isoformat(),
            'ticker_count': len(tickers),
            'data_loaded': len(data),
            'scores': scores,
            'top_20': scores[:20]
        }
        
        # 5. Export if requested
        if export_path:
            with open(export_path, 'w') as f:
                json.dump(results, f, indent=2)
            logging.info(f"\n✓ Results exported to {export_path}")
            broadcaster.broadcast_event(
                "scan",
                f"✓ Results exported to {export_path}",
                level="INFO"
            )
        
        logging.info("\n" + "="*80)
        logging.info("SCAN COMPLETE")
        logging.info("="*80)
        broadcaster.broadcast_event(
            "scan",
            "✅ Parallel scan complete",
            level="INFO"
        )
        
        return results
        
    except Exception as e:
        logging.error(f"Scan failed: {e}", exc_info=True)
        broadcaster.broadcast_event(
            "scan",
            f"❌ Scan failed: {e}",
            level="ERROR"
        )
        return {}


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Parallel Market Scanner - High-Performance Ticker Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--export',
        type=str,
        default='scan_results.json',
        help='Export results to JSON file (default: scan_results.json)'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        default=DEFAULT_WORKERS,
        help=f'Number of worker processes (default: {DEFAULT_WORKERS})'
    )
    
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Force fresh download (ignore cache)'
    )
    
    parser.add_argument(
        '--concurrent',
        type=int,
        default=10,
        help=f'Max concurrent HTTP connections (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Update max concurrent setting
    max_concurrent = args.concurrent
    
    # Run async scan
    results = asyncio.run(
        parallel_scan(
            export_path=args.export,
            workers=args.workers,
            use_cache=not args.no_cache
        )
    )
    
    if results:
        print(f"\n✓ Scan complete: {results['data_loaded']} tickers analyzed")
        print(f"✓ Results exported to {args.export}")


if __name__ == '__main__':
    main()
