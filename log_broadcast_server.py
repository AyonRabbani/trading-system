#!/usr/bin/env python3
"""
WebSocket Broadcast Server for Trading System Live Monitoring
Receives log events from scanner, trading automation, and profit taker
Broadcasts to connected clients (trading_dashboard_viewer.py)
"""

import asyncio
import websockets
import json
import logging
from datetime import datetime
from typing import Set
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Store connected clients
CLIENTS: Set[websockets.WebSocketServerProtocol] = set()

# Store recent events for new clients (last 100 events)
EVENT_HISTORY = []
MAX_HISTORY = 100


async def register_client(websocket):
    """Register a new client connection"""
    CLIENTS.add(websocket)
    logger.info(f"Client connected. Total clients: {len(CLIENTS)}")
    
    # Send event history to new client
    if EVENT_HISTORY:
        try:
            history_message = {
                "type": "history",
                "events": EVENT_HISTORY,
                "count": len(EVENT_HISTORY)
            }
            await websocket.send(json.dumps(history_message))
            logger.info(f"Sent {len(EVENT_HISTORY)} historical events to new client")
        except Exception as e:
            logger.error(f"Error sending history: {e}")


async def unregister_client(websocket):
    """Unregister a client connection"""
    CLIENTS.discard(websocket)
    logger.info(f"Client disconnected. Total clients: {len(CLIENTS)}")


async def broadcast_event(event_data: dict):
    """Broadcast event to all connected clients"""
    if not CLIENTS:
        return
    
    # Add to history
    EVENT_HISTORY.append(event_data)
    if len(EVENT_HISTORY) > MAX_HISTORY:
        EVENT_HISTORY.pop(0)
    
    # Broadcast to all clients
    message = json.dumps(event_data)
    disconnected = set()
    
    for client in CLIENTS:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)
        except Exception as e:
            logger.error(f"Error broadcasting to client: {e}")
            disconnected.add(client)
    
    # Clean up disconnected clients
    for client in disconnected:
        await unregister_client(client)


async def handle_client(websocket, path):
    """Handle incoming client connections and messages"""
    await register_client(websocket)
    
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                
                # Handle different message types
                if data.get("type") == "event":
                    # Event from trading script - broadcast to all viewers
                    await broadcast_event(data)
                    logger.info(f"Broadcast event: {data.get('event_type')} from {data.get('source')}")
                
                elif data.get("type") == "heartbeat":
                    # Heartbeat from script - update system status
                    heartbeat_event = {
                        "type": "heartbeat",
                        "source": data.get("source"),
                        "timestamp": datetime.now().isoformat(),
                        "status": "active"
                    }
                    await broadcast_event(heartbeat_event)
                
                elif data.get("type") == "ping":
                    # Respond to ping
                    await websocket.send(json.dumps({"type": "pong"}))
                
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received: {message}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")
    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        await unregister_client(websocket)


async def periodic_status_broadcast():
    """Periodically broadcast system status"""
    while True:
        await asyncio.sleep(30)  # Every 30 seconds
        
        if CLIENTS:
            status_event = {
                "type": "system_status",
                "timestamp": datetime.now().isoformat(),
                "clients_connected": len(CLIENTS),
                "events_in_history": len(EVENT_HISTORY)
            }
            await broadcast_event(status_event)


async def main(host: str = "localhost", port: int = 8765):
    """Start the WebSocket server"""
    logger.info(f"Starting WebSocket broadcast server on {host}:{port}")
    
    # Start periodic status broadcasts
    asyncio.create_task(periodic_status_broadcast())
    
    # Start WebSocket server
    async with websockets.serve(handle_client, host, port):
        logger.info(f"✓ Server listening on ws://{host}:{port}")
        logger.info("Waiting for connections from trading scripts and viewers...")
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebSocket Broadcast Server for Trading System")
    parser.add_argument("--host", default="localhost", help="Host to bind to (default: localhost)")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind to (default: 8765)")
    args = parser.parse_args()
    
    try:
        asyncio.run(main(args.host, args.port))
    except KeyboardInterrupt:
        logger.info("\nServer shutting down...")
