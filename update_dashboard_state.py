#!/usr/bin/env python3
"""
Update Dashboard State - Refresh public dashboard data

Reads latest scan results and account data, then updates dashboard_state.json
for the public dashboard without requiring a browser visit.

Usage:
    python update_dashboard_state.py
"""

import json
import os
from datetime import datetime
from alpaca.trading.client import TradingClient
from dotenv import load_dotenv

load_dotenv()

def update_dashboard_state():
    """Update dashboard_state.json with latest data"""
    
    # Initialize Alpaca client
    api_key = os.getenv('ALPACA_API_KEY')
    api_secret = os.getenv('ALPACA_SECRET_KEY')
    
    if not api_key or not api_secret:
        print("❌ Error: Alpaca credentials not found in .env")
        return False
    
    trading_client = TradingClient(api_key, api_secret, paper=True)
    
    # Get account data
    account = trading_client.get_account()
    positions = trading_client.get_all_positions()
    
    # Load scan results if available
    scan_data = {}
    if os.path.exists('scan_results.json'):
        with open('scan_results.json', 'r') as f:
            scan_data = json.load(f)
    
    # Build dashboard state
    state = {
        'timestamp': datetime.now().isoformat(),
        'account': {
            'equity': float(account.equity),
            'cash': float(account.cash),
            'buying_power': float(account.buying_power),
            'portfolio_value': float(account.portfolio_value),
            'last_equity': float(account.last_equity),
            'daytrade_count': int(account.daytrade_count),
            'status': account.status,
            'pattern_day_trader': account.pattern_day_trader
        },
        'positions': [
            {
                'symbol': p.symbol,
                'qty': float(p.qty),
                'avg_entry_price': float(p.avg_entry_price),
                'current_price': float(p.current_price),
                'market_value': float(p.market_value),
                'cost_basis': float(p.cost_basis),
                'unrealized_pl': float(p.unrealized_pl),
                'unrealized_plpc': float(p.unrealized_plpc),
                'unrealized_intraday_pl': float(p.unrealized_intraday_pl),
                'unrealized_intraday_plpc': float(p.unrealized_intraday_plpc)
            }
            for p in positions
        ],
        'scanner': {
            'timestamp': scan_data.get('timestamp', ''),
            'market_regime': scan_data.get('market_regime', 'UNKNOWN'),
            'top_scorers': scan_data.get('top_scorers', [])[:10],
            'total_tickers_scored': scan_data.get('total_tickers_scored', 0)
        }
    }
    
    # Save to file
    with open('dashboard_state.json', 'w') as f:
        json.dump(state, f, indent=2)
    
    print(f"✅ Dashboard state updated at {datetime.now().strftime('%H:%M:%S')}")
    print(f"   Portfolio Value: ${state['account']['portfolio_value']:,.2f}")
    print(f"   Positions: {len(state['positions'])}")
    print(f"   Market Regime: {state['scanner']['market_regime']}")
    
    return True


if __name__ == '__main__':
    update_dashboard_state()
