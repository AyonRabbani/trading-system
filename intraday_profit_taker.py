#!/usr/bin/env python3
"""
Intraday Profit Taker - Adaptive Trailing Stop Algorithm

Monitors Alpaca positions in real-time using Polygon WebSocket and applies
statistical analysis to determine optimal trailing stops based on volatility.

Usage:
    python intraday_profit_taker.py --mode aggressive
    python intraday_profit_taker.py --mode conservative --min-profit 3.0
"""

import os
import argparse
import logging
import sys
import time
import requests
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
import numpy as np
import pandas as pd
from massive import WebSocketClient
from massive.websocket.models import WebSocketMessage, Feed, Market
from dotenv import load_dotenv
from event_broadcaster import get_broadcaster

# Load environment variables
load_dotenv()

# Initialize event broadcaster
broadcaster = get_broadcaster(source="Profit Taker")

# Terminal colors
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    GRAY = '\033[90m'
    BRIGHT_GREEN = '\033[1;92m'
    BRIGHT_RED = '\033[1;91m'
    BRIGHT_YELLOW = '\033[1;93m'
    BRIGHT_CYAN = '\033[1;96m'

# ============================================================================
# CONFIGURATION
# ============================================================================

# API Keys
POLYGON_API_KEY = os.getenv('POLYGON_API_KEY')
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Trading Modes
MODES = {
    'aggressive': {
        'profit_threshold': 0.02,      # Start trailing at +2%
        'min_trailing_stop': 0.01,     # Minimum 1% trail
        'max_trailing_stop': 0.03,     # Maximum 3% trail
        'volatility_multiplier': 1.5,  # ATR multiplier for trail width
        'time_decay_factor': 0.7,      # Tighten stops 30% after 2pm
    },
    'moderate': {
        'profit_threshold': 0.03,
        'min_trailing_stop': 0.015,
        'max_trailing_stop': 0.04,
        'volatility_multiplier': 2.0,
        'time_decay_factor': 0.8,
    },
    'conservative': {
        'profit_threshold': 0.05,
        'min_trailing_stop': 0.02,
        'max_trailing_stop': 0.05,
        'volatility_multiplier': 2.5,
        'time_decay_factor': 0.85,
    }
}

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class PositionTracker:
    """Track individual position with statistical analysis."""
    ticker: str
    shares: int
    entry_price: float
    entry_time: datetime
    
    # Price tracking
    current_price: float = 0.0
    peak_price: float = 0.0
    trailing_stop_price: float = 0.0
    
    # Statistical metrics
    price_history: deque = field(default_factory=lambda: deque(maxlen=100))  # Last 100 bars
    returns: deque = field(default_factory=lambda: deque(maxlen=100))
    atr: float = 0.0
    volatility: float = 0.0
    
    # Status
    trailing_active: bool = False
    profit_taken: bool = False
    
    def update_price(self, price: float, timestamp: datetime):
        """Update price and recalculate statistics."""
        self.current_price = price
        self.price_history.append(price)
        
        # Calculate returns
        if len(self.price_history) >= 2:
            ret = (price / self.price_history[-2]) - 1
            self.returns.append(ret)
        
        # Update peak
        if price > self.peak_price:
            self.peak_price = price
        
        # Calculate statistics if enough data
        if len(self.price_history) >= 14:
            self._calculate_statistics()
    
    def _calculate_statistics(self):
        """Calculate ATR and volatility."""
        prices = list(self.price_history)
        
        # Simple ATR approximation from price ranges
        ranges = [abs(prices[i] - prices[i-1]) for i in range(1, len(prices))]
        self.atr = np.mean(ranges[-14:]) if len(ranges) >= 14 else np.mean(ranges)
        
        # Volatility (std dev of returns)
        if len(self.returns) >= 14:
            self.volatility = np.std(list(self.returns))
    
    def get_adaptive_trailing_stop(self, config: dict) -> float:
        """Calculate adaptive trailing stop based on volatility."""
        # Base trailing stop on ATR if available
        if self.atr > 0 and self.current_price > 0:
            # Trail width = volatility * multiplier
            trail_pct = (self.atr / self.current_price) * config['volatility_multiplier']
            
            # Clamp to min/max
            trail_pct = max(config['min_trailing_stop'], 
                          min(config['max_trailing_stop'], trail_pct))
        else:
            # Default to minimum if no data yet
            trail_pct = config['min_trailing_stop']
        
        # Apply time decay (tighter stops as day progresses)
        current_hour = datetime.now().hour
        if current_hour >= 14:  # After 2 PM
            trail_pct *= config['time_decay_factor']
        
        return trail_pct
    
    def get_gain_pct(self) -> float:
        """Calculate current gain percentage."""
        if self.entry_price <= 0:
            return 0.0
        return (self.current_price / self.entry_price) - 1
    
    def get_hold_duration(self) -> timedelta:
        """Get how long position has been held."""
        return datetime.now() - self.entry_time


# ============================================================================
# ALPACA API CLIENT
# ============================================================================

class AlpacaClient:
    """Simplified Alpaca API wrapper."""
    
    def __init__(self, api_key: str, secret_key: str, base_url: str):
        self.base_url = base_url
        self.headers = {
            "accept": "application/json",
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key
        }
    
    def get_positions(self) -> List[Dict]:
        """Get all current positions."""
        url = f"{self.base_url}/v2/positions"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def get_clock(self) -> Dict:
        """Get market clock status."""
        url = f"{self.base_url}/v2/clock"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def close_position(self, symbol: str, qty: Optional[int] = None) -> Dict:
        """Close position (partial or full)."""
        url = f"{self.base_url}/v2/positions/{symbol}"
        
        if qty:
            # Partial close
            params = {"qty": str(qty)}
            response = requests.delete(url, headers=self.headers, params=params)
        else:
            # Full close
            response = requests.delete(url, headers=self.headers)
        
        response.raise_for_status()
        return response.json()


# ============================================================================
# PROFIT TAKER ENGINE
# ============================================================================

class IntraDayProfitTaker:
    """Main engine for intraday profit taking."""
    
    def __init__(self, mode: str = 'moderate', min_profit: float = None):
        self.mode = mode
        self.config = MODES[mode].copy()
        
        # Override min profit if specified
        if min_profit is not None:
            self.config['profit_threshold'] = min_profit / 100.0
        
        # Initialize clients
        self.alpaca = AlpacaClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL)
        self.ws_client = None
        
        # Position tracking
        self.positions: Dict[str, PositionTracker] = {}
        self.subscribed_tickers: set = set()
        
        # Statistics
        self.stats = {
            'profits_taken': 0,
            'total_profit_pct': 0.0,
            'total_profit_dollars': 0.0,
            'avg_hold_minutes': 0.0,
            'trades': []
        }
        
        # Setup logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Configure logging."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'profit_taker_{datetime.now().strftime("%Y%m%d")}.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Track last update times for heartbeat
        self.last_update_times: Dict[str, datetime] = {}
        self.last_heartbeat_time = datetime.now()
        
        # Start heartbeat thread
        self._start_heartbeat_thread()
    
    def initialize_positions(self):
        """Load current Alpaca positions and start tracking."""
        self.logger.info(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
        self.logger.info(f"{Colors.BOLD}{Colors.CYAN}INITIALIZING INTRADAY PROFIT TAKER{Colors.END}")
        self.logger.info(f"{Colors.CYAN}{'='*80}{Colors.END}")
        self.logger.info(f"{Colors.CYAN}Mode: {self.mode.upper()}{Colors.END}")
        self.logger.info(f"{Colors.CYAN}Profit Threshold: {self.config['profit_threshold']*100:.1f}%{Colors.END}")
        self.logger.info(f"{Colors.CYAN}Trailing Stop Range: {self.config['min_trailing_stop']*100:.1f}% - {self.config['max_trailing_stop']*100:.1f}%{Colors.END}")
        self.logger.info("")
        
        # Check market status
        clock = self.alpaca.get_clock()
        if not clock['is_open']:
            self.logger.warning(f"{Colors.YELLOW}⚠️  Market is currently CLOSED{Colors.END}")
            self.logger.info(f"Next open: {clock['next_open']}")
            return False
        
        self.logger.info(f"{Colors.GREEN}✓ Market is OPEN{Colors.END}")
        self.logger.info("")
        
        # Load positions
        alpaca_positions = self.alpaca.get_positions()
        
        if not alpaca_positions:
            self.logger.warning(f"{Colors.YELLOW}No positions found in Alpaca account{Colors.END}")
            return False
        
        self.logger.info(f"{Colors.BOLD}Found {len(alpaca_positions)} positions:{Colors.END}")
        self.logger.info(f"{Colors.GRAY}{'-'*80}{Colors.END}")
        
        for pos in alpaca_positions:
            ticker = pos['symbol']
            shares = float(pos['qty'])
            entry_price = float(pos['avg_entry_price'])
            current_price = float(pos['current_price'])
            unrealized_pl = float(pos['unrealized_pl'])
            unrealized_plpc = float(pos['unrealized_plpc'])
            
            # Color code P&L
            if unrealized_plpc > 0:
                pl_color = Colors.GREEN
            elif unrealized_plpc < -0.02:
                pl_color = Colors.RED
            else:
                pl_color = Colors.YELLOW
            
            # Create tracker
            tracker = PositionTracker(
                ticker=ticker,
                shares=int(shares),
                entry_price=entry_price,
                entry_time=datetime.now(),  # Approximate
                current_price=current_price,
                peak_price=current_price
            )
            
            self.positions[ticker] = tracker
            
            self.logger.info(
                f"{Colors.BOLD}{ticker:6}{Colors.END} | {shares:>6.0f} shares @ ${entry_price:>7.2f} | "
                f"Current: ${current_price:>7.2f} | "
                f"P&L: {pl_color}${unrealized_pl:>8.2f} ({unrealized_plpc*100:>+6.2f}%){Colors.END}"
            )
        
        self.logger.info(f"{Colors.GRAY}{'-'*80}{Colors.END}")
        self.logger.info("")
        return True
    
    def _start_heartbeat_thread(self):
        """Start background thread for periodic status updates."""
        def heartbeat():
            while True:
                time.sleep(60)  # Update every 60 seconds
                
                # Check if we should print update
                if datetime.now() - self.last_heartbeat_time >= timedelta(seconds=60):
                    self._print_status_update()
                    self.last_heartbeat_time = datetime.now()
                    
                    # Also poll Alpaca for current prices (fallback when WebSocket is quiet)
                    if self.positions:
                        self._poll_alpaca_prices()
        
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        self.logger.info(f"{Colors.CYAN}✓ Heartbeat monitor started (60s interval){Colors.END}")
    
    def _print_status_update(self):
        """Print periodic status update."""
        if not self.positions:
            return
        
        self.logger.info("")
        self.logger.info(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.END}")
        self.logger.info(f"{Colors.BOLD}⏱️  HEARTBEAT UPDATE - {datetime.now().strftime('%I:%M:%S %p')}{Colors.END}")
        self.logger.info(f"{Colors.CYAN}{'='*80}{Colors.END}")
        
        for ticker, pos in self.positions.items():
            gain_pct = pos.get_gain_pct()
            status = f"{Colors.BRIGHT_GREEN}TRAILING{Colors.END}" if pos.trailing_active else f"{Colors.GRAY}WATCHING{Colors.END}"
            
            # Color code the gain
            if gain_pct > 0:
                gain_color = Colors.BRIGHT_GREEN
            elif gain_pct < -0.02:
                gain_color = Colors.BRIGHT_RED
            else:
                gain_color = Colors.YELLOW
            
            # Last update info
            last_update = self.last_update_times.get(ticker)
            if last_update:
                staleness = (datetime.now() - last_update).total_seconds() / 60
                time_str = f"({staleness:.0f}m ago)" if staleness > 1 else "(just now)"
            else:
                time_str = "(no data yet)"
            
            self.logger.info(
                f"{ticker:6} | Status: {status} | "
                f"Price: ${pos.current_price:.2f} | "
                f"Gain: {gain_color}{gain_pct*100:+.2f}%{Colors.END} | "
                f"Peak: ${pos.peak_price:.2f} | "
                f"{Colors.GRAY}Updated {time_str}{Colors.END}"
            )
            
            # Show trailing stop info if active
            if pos.trailing_active:
                distance_to_stop = ((pos.current_price / pos.trailing_stop_price) - 1) * 100
                self.logger.info(
                    f"       └─ Stop: ${pos.trailing_stop_price:.2f} "
                    f"({distance_to_stop:.1f}% away)"
                )
        
        self.logger.info(f"{Colors.CYAN}{'='*80}{Colors.END}")
        self.logger.info("")
    
    def _poll_alpaca_prices(self):
        """Poll Alpaca REST API for current prices (fallback when WebSocket quiet)."""
        try:
            alpaca_positions = self.alpaca.get_positions()
            
            if not alpaca_positions:
                return
            
            self.logger.debug(f"{Colors.GRAY}Polling Alpaca for current prices...{Colors.END}")
            
            for pos_data in alpaca_positions:
                ticker = pos_data['symbol']
                if ticker in self.positions:
                    price = float(pos_data['current_price'])
                    self.logger.info(f"{Colors.GRAY}📊 Alpaca Poll: {ticker} @ ${price:.2f}{Colors.END}")
                    self._update_position(ticker, price, datetime.now())
                    
        except Exception as e:
            self.logger.debug(f"Error polling Alpaca prices: {e}")
    
    def start_websocket(self):
        """Start Polygon WebSocket for real-time data."""
        self.logger.info("Starting WebSocket connection...")
        
        try:
            # Initialize WebSocket client
            self.ws_client = WebSocketClient(
                api_key=POLYGON_API_KEY,
                feed=Feed.Delayed,
                market=Market.Stocks
            )
            
            # Subscribe to aggregate bars for all tracked tickers
            subscriptions = [f"AM.{ticker}" for ticker in self.positions.keys()]
            self.logger.info(f"{Colors.CYAN}Subscribing to: {', '.join(subscriptions)}{Colors.END}")
            
            # Subscribe to ALL tickers at once (pass as multiple arguments)
            if subscriptions:
                self.ws_client.subscribe(*subscriptions)  # Unpack list as separate arguments
                self.logger.info(f"{Colors.GREEN}  ✓ Subscribed to {len(subscriptions)} tickers{Colors.END}")
            
            self.logger.info("")
            self.logger.info(f"{Colors.GREEN}✓ Subscriptions registered{Colors.END}")
            self.logger.info(f"{Colors.YELLOW}⚠️  Note: Using delayed feed (15-minute lag){Colors.END}")
            self.logger.info(f"{Colors.CYAN}💡 Heartbeat will poll Alpaca every 60s for price updates{Colors.END}")
            self.logger.info("")
            self.logger.info(f"{Colors.BOLD}{Colors.GREEN}{'='*80}{Colors.END}")
            self.logger.info(f"{Colors.BOLD}{Colors.GREEN}MONITORING STARTED - Watching for profit opportunities...{Colors.END}")
            self.logger.info(f"{Colors.GREEN}{'='*80}{Colors.END}")
            self.logger.info("")
            
            # Start listening (blocking call)
            self.logger.info(f"{Colors.CYAN}Connecting to Polygon WebSocket...{Colors.END}")
            self.ws_client.run(self._handle_websocket_message)
            
        except Exception as e:
            self.logger.error(f"{Colors.RED}WebSocket connection error: {e}{Colors.END}")
            import traceback
            self.logger.error(f"{Colors.RED}{traceback.format_exc()}{Colors.END}")
            self.logger.warning(f"{Colors.YELLOW}Falling back to Alpaca polling only...{Colors.END}")
            
            # Fallback: just use heartbeat polling
            self.logger.info("")
            self.logger.info(f"{Colors.BOLD}{Colors.YELLOW}{'='*80}{Colors.END}")
            self.logger.info(f"{Colors.BOLD}{Colors.YELLOW}MONITORING STARTED (Polling Mode - WebSocket unavailable){Colors.END}")
            self.logger.info(f"{Colors.YELLOW}{'='*80}{Colors.END}")
            self.logger.info(f"{Colors.CYAN}Using Alpaca REST API polling every 30 seconds{Colors.END}")
            self.logger.info("")
            
            # Keep alive with polling only
            try:
                while True:
                    time.sleep(30)
                    self._poll_alpaca_prices()
            except KeyboardInterrupt:
                pass
    
    def _handle_websocket_message(self, msgs: List[WebSocketMessage]):
        """Process incoming WebSocket messages."""
        try:
            for msg in msgs:
                self.logger.debug(f"Received message: {msg}")
                
                # Parse message - use correct attribute names for EquityAgg
                ticker = getattr(msg, 'symbol', getattr(msg, 'sym', None))
                close_price = getattr(msg, 'close', getattr(msg, 'c', None))
                end_time = getattr(msg, 'end_timestamp', getattr(msg, 'e', None))
                
                if not ticker or ticker not in self.positions:
                    continue
                
                if not close_price or not end_time:
                    self.logger.warning(f"{Colors.YELLOW}Incomplete data for {ticker}{Colors.END}")
                    continue
                
                close_price = float(close_price)
                timestamp = datetime.fromtimestamp(end_time / 1000)  # Convert ms to datetime
                
                # Log WebSocket data received
                self.logger.info(f"{Colors.CYAN}📡 WebSocket: {ticker} @ ${close_price:.2f}{Colors.END}")
                
                # Update position
                self._update_position(ticker, close_price, timestamp)

        except Exception as e:
            self.logger.error(f"{Colors.RED}Error handling WebSocket message: {e}{Colors.END}")
            import traceback
            self.logger.error(f"{Colors.RED}{traceback.format_exc()}{Colors.END}")
    
    def _update_position(self, ticker: str, price: float, timestamp: datetime):
        """Update position and check for profit-taking opportunity."""
        if ticker not in self.positions:
            return
        
        # Track last update time
        self.last_update_times[ticker] = timestamp
        
        pos = self.positions[ticker]
        pos.update_price(price, timestamp)
        
        # Calculate gain
        gain_pct = pos.get_gain_pct()
        
        # Check if profit threshold reached
        if gain_pct >= self.config['profit_threshold']:
            
            # Activate trailing stop if not already active
            if not pos.trailing_active:
                pos.trailing_active = True
                trail_pct = pos.get_adaptive_trailing_stop(self.config)
                pos.trailing_stop_price = pos.peak_price * (1 - trail_pct)
                
                self.logger.info(
                    f"{Colors.BRIGHT_GREEN}🎯 {ticker} | TRAILING ACTIVATED{Colors.END} at "
                    f"{Colors.BRIGHT_GREEN}+{gain_pct*100:.2f}%{Colors.END} | "
                    f"Peak: ${pos.peak_price:.2f} | "
                    f"Stop: ${pos.trailing_stop_price:.2f} ({trail_pct*100:.2f}% trail) | "
                    f"ATR: ${pos.atr:.3f} | Vol: {pos.volatility*100:.2f}%"
                )
            
            # Update trailing stop if new peak
            elif price > pos.peak_price:
                trail_pct = pos.get_adaptive_trailing_stop(self.config)
                pos.trailing_stop_price = pos.peak_price * (1 - trail_pct)
                
                self.logger.info(
                    f"{Colors.BRIGHT_GREEN}📈 {ticker} | NEW PEAK{Colors.END} "
                    f"${pos.peak_price:.2f} ({Colors.BRIGHT_GREEN}+{gain_pct*100:.2f}%{Colors.END}) | "
                    f"Stop raised to ${pos.trailing_stop_price:.2f}"
                )
            
            # Check if trailing stop hit
            if price <= pos.trailing_stop_price:
                self._take_profit(ticker, price, gain_pct)
        
        # Force exit 5 minutes before close
        elif timestamp.time().hour == 15 and timestamp.time().minute >= 55:
            if gain_pct > 0.01:  # Any profit > 1%
                self.logger.info(f"{Colors.YELLOW}⏰ {ticker} | FORCE EXIT before close{Colors.END}")
                self._take_profit(ticker, price, gain_pct)
    
    def _take_profit(self, ticker: str, price: float, gain_pct: float):
        """Execute profit-taking sell order."""
        pos = self.positions[ticker]
        
        self.logger.info("")
        self.logger.info(f"{Colors.BOLD}{Colors.GREEN}{'='*80}{Colors.END}")
        self.logger.info(f"{Colors.BOLD}{Colors.GREEN}💰 TAKING PROFIT: {ticker}{Colors.END}")
        self.logger.info(f"{Colors.GREEN}{'-'*80}{Colors.END}")
        
        try:
            # Close position via Alpaca
            result = self.alpaca.close_position(ticker)
            
            # Calculate profit
            hold_duration = pos.get_hold_duration()
            profit_dollars = pos.shares * (price - pos.entry_price)
            
            self.logger.info(f"Entry:     ${pos.entry_price:.2f}")
            self.logger.info(f"Peak:      ${pos.peak_price:.2f} (+{((pos.peak_price/pos.entry_price)-1)*100:.2f}%)")
            self.logger.info(f"Exit:      ${price:.2f}")
            self.logger.info(f"Gain:      {Colors.BRIGHT_GREEN}+{gain_pct*100:.2f}%{Colors.END}")
            self.logger.info(f"Profit:    {Colors.BRIGHT_GREEN}${profit_dollars:,.2f}{Colors.END}")
            self.logger.info(f"Shares:    {pos.shares}")
            self.logger.info(f"Hold Time: {hold_duration}")
            self.logger.info(f"Order ID:  {result.get('id', 'N/A')}")
            
            # Broadcast profit-taking event
            broadcaster.broadcast_event(
                event_type="profit",
                message=f"💰 PROFIT TAKEN: {ticker} +{gain_pct*100:.1f}% (${profit_dollars:,.2f})",
                level="INFO",
                ticker=ticker,
                entry_price=pos.entry_price,
                exit_price=price,
                gain_pct=gain_pct * 100,
                profit_dollars=profit_dollars,
                shares=pos.shares,
                hold_time=hold_duration
            )
            
            # Update statistics
            self.stats['profits_taken'] += 1
            self.stats['total_profit_pct'] += gain_pct
            self.stats['total_profit_dollars'] += profit_dollars
            self.stats['trades'].append({
                'ticker': ticker,
                'entry': pos.entry_price,
                'exit': price,
                'gain_pct': gain_pct,
                'profit': profit_dollars,
                'hold_minutes': hold_duration.total_seconds() / 60
            })
            
            # Remove from tracking
            del self.positions[ticker]
            
            self.logger.info(f"{Colors.GREEN}✓ Position closed successfully{Colors.END}")
            
        except Exception as e:
            self.logger.error(f"{Colors.RED}✗ Error closing position: {e}{Colors.END}")
        
        self.logger.info(f"{Colors.GREEN}{'='*80}{Colors.END}")
        self.logger.info("")
        
        # Print updated stats
        self._print_stats()
    
    def _print_stats(self):
        """Print current session statistics."""
        if self.stats['profits_taken'] == 0:
            return
        
        avg_gain = self.stats['total_profit_pct'] / self.stats['profits_taken']
        avg_hold = np.mean([t['hold_minutes'] for t in self.stats['trades']])
        
        self.logger.info(f"{Colors.BOLD}{Colors.CYAN}📊 SESSION STATISTICS:{Colors.END}")
        self.logger.info(f"{Colors.CYAN}   Profits Taken:   {self.stats['profits_taken']}{Colors.END}")
        self.logger.info(f"{Colors.GREEN}   Total Profit:    ${self.stats['total_profit_dollars']:,.2f}{Colors.END}")
        self.logger.info(f"{Colors.GREEN}   Average Gain:    {avg_gain*100:.2f}%{Colors.END}")
        self.logger.info(f"{Colors.CYAN}   Avg Hold Time:   {avg_hold:.0f} minutes{Colors.END}")
        self.logger.info(f"{Colors.CYAN}   Active Positions: {len(self.positions)}{Colors.END}")
        self.logger.info("")
    
    def run(self):
        """Main run loop."""
        try:
            # Initialize
            if not self.initialize_positions():
                self.logger.error("Failed to initialize - exiting")
                return
            
            # Start monitoring
            self.start_websocket()
            
        except KeyboardInterrupt:
            self.logger.info(f"\n\n{Colors.YELLOW}⚠️  Shutting down gracefully...{Colors.END}")
            self._print_stats()
            self.logger.info(f"{Colors.CYAN}Goodbye!{Colors.END}")
        except Exception as e:
            self.logger.error(f"{Colors.RED}Fatal error: {e}{Colors.END}")
            import traceback
            self.logger.error(traceback.format_exc())


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Intraday Profit Taker - Adaptive Trailing Stop Algorithm',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in moderate mode (default)
  python intraday_profit_taker.py
  
  # Run in aggressive mode (tighter stops, faster profits)
  python intraday_profit_taker.py --mode aggressive
  
  # Run in conservative mode with custom min profit
  python intraday_profit_taker.py --mode conservative --min-profit 5.0
  
  # Show current positions without trading
  python intraday_profit_taker.py --dry-run
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['aggressive', 'moderate', 'conservative'],
        default='moderate',
        help='Trading mode (default: moderate)'
    )
    
    parser.add_argument(
        '--min-profit',
        type=float,
        metavar='PCT',
        help='Minimum profit %% to start trailing (overrides mode default)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show positions but do not trade'
    )
    
    args = parser.parse_args()
    
    # Create and run profit taker
    profit_taker = IntraDayProfitTaker(
        mode=args.mode,
        min_profit=args.min_profit
    )
    
    if args.dry_run:
        profit_taker.initialize_positions()
        print("\nDry-run mode - not starting monitoring")
        return
    
    profit_taker.run()


if __name__ == '__main__':
    main()
