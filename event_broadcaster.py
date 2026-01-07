"""
WebSocket Event Broadcaster
Helper module for sending events to the log broadcast server AND public JSON
Dual-logs to both WebSocket (local real-time) and JSON file (public cloud sync)
"""

import asyncio
import websockets
import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class EventBroadcaster:
    """Non-blocking WebSocket client for broadcasting events"""
    
    def __init__(self, server_url: str = "ws://localhost:8765", source: str = "unknown"):
        self.server_url = server_url
        self.source = source
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self._loop = None
        self._connect_task = None
        
        # Initialize public exporter for cloud sync
        try:
            from public_event_exporter import get_exporter
            self.public_exporter = get_exporter()
            self.export_public = True
            logger.info("Public event exporter initialized")
        except Exception as e:
            logger.warning(f"Public exporter not available: {e}")
            self.export_public = False
    
    def start(self):
        """Start the broadcaster in the background"""
        try:
            # Try to connect asynchronously
            self._loop = asyncio.new_event_loop()
            self._connect_task = self._loop.create_task(self._connect())
            # Don't block - run in background thread
            import threading
            thread = threading.Thread(target=self._run_loop, daemon=True)
            thread.start()
            logger.info(f"EventBroadcaster started for {self.source}")
        except Exception as e:
            logger.warning(f"Could not start broadcaster: {e}")
    
    def _run_loop(self):
        """Run the event loop in a background thread"""
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        except Exception as e:
            logger.error(f"Event loop error: {e}")
    
    async def _connect(self):
        """Establish WebSocket connection"""
        try:
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            logger.info(f"Connected to broadcast server at {self.server_url}")
        except Exception as e:
            logger.warning(f"Could not connect to broadcast server: {e}")
            self.connected = False
    
    def broadcast_event(self, event_type: str, message: str, level: str = "INFO", **kwargs):
        """
        Broadcast an event to BOTH WebSocket server AND public JSON file.
        WebSocket = real-time local viewing
        JSON = cloud sync for public viewer
        
        Args:
            event_type: Type of event (scan, strategy, order, profit, info, warning, error)
            message: Event message
            level: Log level
            **kwargs: Additional event data
        """
        # ALWAYS log to public JSON (sanitized, for cloud sync)
        if self.export_public:
            try:
                self.public_exporter.add_event(
                    event_type=event_type,
                    message=message,
                    source=self.source,
                    metadata=kwargs,
                    level=level
                )
            except Exception as e:
                logger.error(f"Error logging to public exporter: {e}")
        
        # TRY to send to WebSocket (local only, best effort)
        if not self.connected or not self._loop:
            return
        
        event_data = {
            "type": "event",
            "source": self.source,
            "event_type": event_type,
            "level": level,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            **kwargs
        }
        
        # Schedule the send on the event loop (non-blocking)
        asyncio.run_coroutine_threadsafe(self._send_event(event_data), self._loop)
    
    async def _send_event(self, event_data: dict):
        """Send event to server"""
        try:
            if self.websocket and self.connected:
                await self.websocket.send(json.dumps(event_data))
        except websockets.exceptions.ConnectionClosed:
            self.connected = False
            logger.warning("Connection to broadcast server lost")
        except Exception as e:
            logger.error(f"Error sending event: {e}")
    
    def send_heartbeat(self):
        """Send heartbeat to indicate script is alive"""
        if not self.connected or not self._loop:
            return
        
        heartbeat_data = {
            "type": "heartbeat",
            "source": self.source,
            "timestamp": datetime.now().isoformat()
        }
        
        asyncio.run_coroutine_threadsafe(
            self._send_event(heartbeat_data), 
            self._loop
        )
    
    def close(self):
        """Close the connection and save public events"""
        # Save public events before closing
        if self.export_public:
            try:
                self.public_exporter.force_save()
                logger.info("Public events saved on close")
            except Exception as e:
                logger.error(f"Error saving public events: {e}")
        
        # Close WebSocket
        if self._loop and self.websocket:
            asyncio.run_coroutine_threadsafe(self.websocket.close(), self._loop)
            self._loop.stop()
        self.connected = False


# Singleton broadcaster instance
_broadcaster: Optional[EventBroadcaster] = None


def get_broadcaster(source: str = "unknown") -> EventBroadcaster:
    """Get or create the global broadcaster instance"""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = EventBroadcaster(source=source)
        _broadcaster.start()
    return _broadcaster
