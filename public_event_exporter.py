#!/usr/bin/env python3
"""
Public Event Exporter
Exports full trading events to JSON for team monitoring via GitHub/cloud sharing.
NO SANITIZATION - Full data visibility for friends and team.
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional
from collections import deque
import threading
import time
import logging

logger = logging.getLogger(__name__)


class PublicEventExporter:
    """Exports sanitized events to JSON for public sharing"""
    
    def __init__(self, output_file: str = "public_events.json", max_events: int = 200):
        self.output_file = output_file
        self.max_events = max_events
        self.events: deque = deque(maxlen=max_events)
        self.lock = threading.Lock()
        self.auto_save_enabled = True
        
        # Load existing events
        self._load_events()
        
        # Start auto-save thread
        self._start_auto_save()
    
    def _load_events(self):
        """Load existing events from file"""
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, 'r') as f:
                    data = json.load(f)
                    existing = data.get('events', [])
                    self.events = deque(existing, maxlen=self.max_events)
                    logger.info(f"Loaded {len(existing)} existing public events")
            except Exception as e:
                logger.warning(f"Could not load existing events: {e}")
    
    def add_event(self, event_type: str, message: str, source: str, 
                  metadata: Optional[Dict] = None, level: str = "INFO"):
        """
        Add a sanitized event for public consumption.
        
        Args:
            event_type: Type of event (scan, strategy, order, profit, etc.)
            message: Human-readable message (will be sanitized)
            source: Source system (Scanner, Trading, Profit Taker)
            metadata: Additional context (will be sanitized)
            level: Log level (INFO, WARNING, ERROR)
        """
        with self.lock:
            event = {
                'timestamp': datetime.now().isoformat(),
                'type': event_type,
                'level': level,
                'source': source,
                'message': message,  # Full message - no sanitization
                'metadata': metadata or {}  # Full metadata - no sanitization
            }
            
            self.events.append(event)
    
    def _sanitize_message(self, message: str) -> str:
        """Keep full message - no sanitization for team monitoring"""
        return message
    
    def _sanitize_metadata(self, metadata: Dict) -> Dict:
        """Keep all metadata - no sanitization for team monitoring"""
        return metadata
    
    def _save_events(self):
        """Save events to JSON file"""
        with self.lock:
            try:
                data = {
                    'last_updated': datetime.now().isoformat(),
                    'event_count': len(self.events),
                    'events': list(self.events)
                }
                
                # Write atomically (write to temp, then rename)
                temp_file = f"{self.output_file}.tmp"
                with open(temp_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                os.replace(temp_file, self.output_file)
                
            except Exception as e:
                logger.error(f"Error saving events: {e}")
    
    def _start_auto_save(self):
        """Start background thread to auto-save every 30 seconds"""
        def auto_save_loop():
            while self.auto_save_enabled:
                time.sleep(30)
                if self.events:
                    self._save_events()
        
        thread = threading.Thread(target=auto_save_loop, daemon=True)
        thread.start()
        logger.info("Auto-save thread started (every 30s)")
    
    def get_summary(self) -> Dict:
        """Get event summary statistics"""
        with self.lock:
            event_types = {}
            for event in self.events:
                event_type = event['type']
                event_types[event_type] = event_types.get(event_type, 0) + 1
            
            return {
                'total_events': len(self.events),
                'by_type': event_types,
                'last_event': self.events[-1] if self.events else None,
                'last_updated': datetime.now().isoformat()
            }
    
    def force_save(self):
        """Force immediate save (call before shutdown)"""
        self._save_events()
        logger.info(f"Saved {len(self.events)} public events to {self.output_file}")
    
    def stop(self):
        """Stop auto-save and save final state"""
        self.auto_save_enabled = False
        self.force_save()


# Global exporter instance
_exporter: Optional[PublicEventExporter] = None


def get_exporter() -> PublicEventExporter:
    """Get or create the global exporter instance"""
    global _exporter
    if _exporter is None:
        _exporter = PublicEventExporter()
    return _exporter


def log_public_event(event_type: str, message: str, source: str, 
                     metadata: Optional[Dict] = None, level: str = "INFO"):
    """
    Convenience function to log a public event.
    
    Usage:
        from public_event_exporter import log_public_event
        
        log_public_event(
            event_type='scan',
            message='Market scan completed - Top scorer: RKLB (89.0)',
            source='Market Scanner',
            metadata={'top_ticker': 'RKLB', 'score': 89.0}
        )
    """
    exporter = get_exporter()
    exporter.add_event(event_type, message, source, metadata, level)


if __name__ == "__main__":
    # Test the exporter
    print("Testing Public Event Exporter...")
    
    exporter = get_exporter()
    
    # Add test events
    exporter.add_event(
        'scan',
        'Market scan started - analyzing 110 tickers',
        'Market Scanner',
        {'ticker_count': 110}
    )
    
    exporter.add_event(
        'strategy',
        'Selected CORE strategy | NAV: $125,432.50',
        'Trading Automation',
        {'strategy_name': 'CORE', 'nav': 125432.50}
    )
    
    exporter.add_event(
        'order',
        'BUY 150 NVDA (MARKET)',
        'Trading Automation',
        {'action': 'BUY', 'ticker': 'NVDA', 'quantity': 150}
    )
    
    exporter.add_event(
        'profit',
        'PROFIT TAKEN: TSLA +6.3% ($3,247.80)',
        'Profit Taker',
        {'ticker': 'TSLA', 'gain_pct': 6.3, 'profit_dollars': 3247.80}
    )
    
    # Save immediately
    exporter.force_save()
    
    print(f"\n✅ Test complete! Check {exporter.output_file}")
    print(f"   Events saved: {len(exporter.events)}")
    print(f"\nSummary:")
    print(json.dumps(exporter.get_summary(), indent=2))
