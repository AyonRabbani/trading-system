#!/usr/bin/env python3
"""
Ticker Universe Downloader - Massive (Polygon.io) Flat-File Integration

Downloads daily flat-file of 10K+ US stock tickers from Massive S3-compatible API.
Extracts unique tickers and filters for quality (volume, price thresholds).
"""

import boto3
from botocore.config import Config
import gzip
import csv
import logging
from datetime import datetime, timedelta
import os
from typing import List, Set
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Massive API Credentials
MASSIVE_ACCESS_KEY = '6ee41e5c-10a9-455b-b1e6-e4ebf9580ee2'
MASSIVE_SECRET_KEY = 'ANeN7iKkqpD0bW2RcI_2xWVbNljnDCZ5'
MASSIVE_ENDPOINT = 'https://files.massive.com'
BUCKET_NAME = 'flatfiles'

# Quality filters
MIN_VOLUME = 100000  # Minimum 100K daily volume
MIN_PRICE = 1.0      # Minimum $1 per share
MAX_PRICE = 10000.0  # Maximum $10K per share (filter out errors)

class TickerDownloader:
    """Download and process ticker universe from Massive flat-files"""
    
    def __init__(self, cache_dir='./data'):
        """Initialize downloader with S3 client"""
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # Initialize S3 client
        session = boto3.Session(
            aws_access_key_id=MASSIVE_ACCESS_KEY,
            aws_secret_access_key=MASSIVE_SECRET_KEY,
        )
        
        self.s3 = session.client(
            's3',
            endpoint_url=MASSIVE_ENDPOINT,
            config=Config(signature_version='s3v4'),
        )
        
        logging.info("Ticker downloader initialized with Massive API")
    
    def get_latest_date(self) -> str:
        """Get most recent trading date (always use previous close 2026-01-07)"""
        # Always use 2026-01-07 as requested - this file exists
        latest_date = '2026-01-07'
        logging.info(f"Using previous close date: {latest_date}")
        return latest_date
    
    def download_flatfile(self, date: str = None) -> str:
        """
        Download daily flat-file from Massive
        
        Args:
            date: Date string 'YYYY-MM-DD' (default: latest trading day)
        
        Returns:
            Path to downloaded file
        """
        if date is None:
            date = self.get_latest_date()
        
        # Parse date
        dt = datetime.strptime(date, '%Y-%m-%d')
        
        # Construct S3 object key (matching example format)
        object_key = f"flatfiles/us_stocks_sip/day_aggs_v1/{dt.year}/{dt.month:02d}/{date}.csv.gz"
        
        # Remove bucket name prefix if present (as shown in example)
        if object_key.startswith(BUCKET_NAME + '/'):
            object_key = object_key[len(BUCKET_NAME + '/'):]
        
        # Local file path
        local_file_name = f"{date}.csv.gz"
        local_file_path = os.path.join(self.cache_dir, local_file_name)
        
        # Check if already downloaded today
        if os.path.exists(local_file_path):
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(local_file_path))
            if file_age.total_seconds() < 86400:  # Less than 24 hours old
                logging.info(f"Using cached file: {local_file_path}")
                return local_file_path
        
        # Download file
        logging.info(f"Downloading '{object_key}' from bucket '{BUCKET_NAME}'...")
        logging.info(f"Full S3 path: s3://{BUCKET_NAME}/{object_key}")
        try:
            self.s3.download_file(BUCKET_NAME, object_key, local_file_path)
            logging.info(f"Downloaded to {local_file_path}")
            return local_file_path
        except Exception as e:
            logging.error(f"Failed to download flat-file: {e}")
            # Try to list available files to debug
            try:
                logging.info("Attempting to list available files...")
                response = self.s3.list_objects_v2(
                    Bucket=BUCKET_NAME,
                    Prefix=f"flatfiles/us_stocks_sip/day_aggs_v1/{dt.year}/{dt.month:02d}/",
                    MaxKeys=10
                )
                if 'Contents' in response:
                    logging.info(f"Found {len(response['Contents'])} files in directory:")
                    for obj in response['Contents'][:5]:
                        logging.info(f"  - {obj['Key']}")
                else:
                    logging.warning("No files found in directory")
            except Exception as list_err:
                logging.error(f"Could not list files: {list_err}")
            raise
    
    def extract_tickers(self, filepath: str, apply_filters: bool = True) -> List[str]:
        """
        Extract unique tickers from compressed flat-file
        
        Args:
            filepath: Path to .csv.gz file
            apply_filters: Apply volume/price quality filters
        
        Returns:
            Sorted list of ticker symbols
        """
        logging.info(f"Extracting tickers from {filepath}...")
        tickers = set()
        total_rows = 0
        filtered_rows = 0
        
        try:
            with gzip.open(filepath, 'rt') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    total_rows += 1
                    
                    ticker = row.get('ticker', '').strip().upper()
                    if not ticker:
                        continue
                    
                    # Apply quality filters
                    if apply_filters:
                        try:
                            volume = float(row.get('volume', 0))
                            close = float(row.get('close', 0))
                            
                            # Filter criteria
                            if volume < MIN_VOLUME:
                                filtered_rows += 1
                                continue
                            
                            if close < MIN_PRICE or close > MAX_PRICE:
                                filtered_rows += 1
                                continue
                        except (ValueError, TypeError):
                            filtered_rows += 1
                            continue
                    
                    tickers.add(ticker)
            
            ticker_list = sorted(list(tickers))
            logging.info(f"Extracted {len(ticker_list)} unique tickers from {total_rows} rows")
            if apply_filters:
                logging.info(f"Filtered out {filtered_rows} rows (volume < {MIN_VOLUME}, price < ${MIN_PRICE})")
            
            return ticker_list
        
        except Exception as e:
            logging.error(f"Failed to extract tickers: {e}")
            raise
    
    def get_ticker_universe(self, date: str = None, apply_filters: bool = True) -> List[str]:
        """
        Main method: Download and extract ticker universe
        
        Args:
            date: Date string 'YYYY-MM-DD' (default: latest)
            apply_filters: Apply quality filters
        
        Returns:
            List of ticker symbols
        """
        try:
            # Download flat-file
            filepath = self.download_flatfile(date)
            
            # Extract tickers
            tickers = self.extract_tickers(filepath, apply_filters)
            
            return tickers
        
        except Exception as e:
            logging.error(f"Failed to get ticker universe: {e}")
            # Fallback to empty list (scanner will use fallback universe)
            return []
    
    def save_to_cache(self, tickers: List[str], filename: str = 'ticker_cache.txt'):
        """Save ticker list to cache file"""
        cache_path = os.path.join(self.cache_dir, filename)
        with open(cache_path, 'w') as f:
            f.write('\n'.join(tickers))
        logging.info(f"Saved {len(tickers)} tickers to {cache_path}")
    
    def load_from_cache(self, filename: str = 'ticker_cache.txt') -> List[str]:
        """Load ticker list from cache file"""
        cache_path = os.path.join(self.cache_dir, filename)
        if not os.path.exists(cache_path):
            return []
        
        with open(cache_path, 'r') as f:
            tickers = [line.strip().upper() for line in f if line.strip()]
        
        logging.info(f"Loaded {len(tickers)} tickers from cache")
        return tickers


def main():
    """Test ticker download"""
    downloader = TickerDownloader()
    
    # Download and extract
    tickers = downloader.get_ticker_universe(apply_filters=True)
    
    print(f"\n{'='*60}")
    print(f"TICKER UNIVERSE SUMMARY")
    print(f"{'='*60}")
    print(f"Total tickers: {len(tickers)}")
    print(f"\nFirst 20 tickers: {', '.join(tickers[:20])}")
    print(f"Last 20 tickers: {', '.join(tickers[-20:])}")
    
    # Save to cache
    downloader.save_to_cache(tickers)
    
    # Test cache load
    cached = downloader.load_from_cache()
    print(f"\nCache verification: {len(cached)} tickers loaded")


if __name__ == '__main__':
    main()
