#!/usr/bin/env python3
import os, argparse, requests, pandas as pd, numpy as np, json, time, logging
from datetime import datetime, timedelta
from typing import Dict, Tuple, List, Optional
from dotenv import load_dotenv
from event_broadcaster import get_broadcaster

load_dotenv()
broadcaster = get_broadcaster(source="Portfolio Manager")

POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

LOOKBACK_DAYS = 10
SHARPE_LOOKBACK = 30
DRAWDOWN_THRESHOLD = 0.05
DRAWDOWN_LOOKBACK = 5
COOLDOWN_DAYS = 5
PM_MOMENTUM_LOOKBACK = 20
CAPITAL = 100000
SCAN_RESULTS_FILE = 'scan_results.json'
STATE_FILE = 'pm_state.json'

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_static_buckets():
    return {
        'BENCHMARKS': ["SPY", "QQQ"],
        'TICKERS': ["GLD", "SLX", "JEF", "CPER"],
        'SPECULATIVE': ["NVDA", "PLTR", "TSLA", "MSFT"],
        'ASYMMETRIC': ["OKLO", "RMBS", "QBTS", "IREN", "AFRM", "SOFI"]
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['live', 'dry-run'], default='dry-run')
    parser.add_argument('--use-scanner', action='store_true')
    args = parser.parse_args()
    
    print("Portfolio Manager - Implementation in progress")
    print("Using static buckets for now")
    buckets = get_static_buckets()
    print(f"Loaded {len(buckets)} buckets")

if __name__ == '__main__':
    main()
