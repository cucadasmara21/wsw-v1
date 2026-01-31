"""
Prophecy Engine: WebSocket endpoint for real-time market data.
Pushes cached quotes at cadence_ms without hammering providers.
"""
import logging
import json
import time
import asyncio
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect

from services.data_provider_service import _data_provider_service

logger = logging.getLogger(__name__)


class MarketBroadcaster:
    """Manages WebSocket connections and broadcasts market quotes"""
    
    def __init__(self):
        self.connections: Dict[WebSocket, Dict[str, any]] = {}  # ws -> {symbols: set, cadence_ms: int}
        self._refresh_tasks: Dict[str, asyncio.Task] = {}  # symbol -> refresh task
    
    async def connect(self, websocket: WebSocket):
        """Add a new WebSocket connection"""
        await websocket.accept()
        self.connections[websocket] = {"symbols": set(), "cadence_ms": 250}
        logger.info(f"Market WS client connected (total: {len(self.connections)})")
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.connections:
            del self.connections[websocket]
            logger.info(f"Market WS client disconnected (total: {len(self.connections)})")
    
    async def handle_subscription(self, websocket: WebSocket, message: dict):
        """Handle subscription message: {type:"subscribe", symbols:["AAPL"], cadence_ms:250}"""
        if message.get("type") == "subscribe":
            symbols = message.get("symbols", [])
            cadence_ms = max(100, min(5000, message.get("cadence_ms", 250)))  # Clamp 100-5000ms
            
            if websocket in self.connections:
                self.connections[websocket]["symbols"] = set(symbols)
                self.connections[websocket]["cadence_ms"] = cadence_ms
                logger.info(f"Client subscribed to {len(symbols)} symbols at {cadence_ms}ms cadence")
                await websocket.send_json({"type": "subscribed", "symbols": symbols, "cadence_ms": cadence_ms})
    
    async def broadcast_quotes(self):
        """Broadcast cached quotes to all subscribed clients at their cadence"""
        if not self.connections:
            return
        
        # Collect all unique symbols from all clients
        all_symbols = set()
        for conn_data in self.connections.values():
            all_symbols.update(conn_data["symbols"])
        
        if not all_symbols:
            return
        
        # Get cached quotes (non-blocking, O(1))
        quotes = {}
        for symbol in all_symbols:
            resolved_ticker = _data_provider_service.resolve_ticker(symbol)
            cached = _data_provider_service.get_cached_quote(resolved_ticker)
            if cached:
                quotes[symbol] = {
                    "last": cached.get("last"),
                    "change_pct": cached.get("change_pct"),
                    "shock": None,  # Would need to decode from meta32 or fetch separately
                    "risk": None,
                    "stale": cached.get("stale", False)
                }
            else:
                # Try stale cache
                stale = _data_provider_service.get_stale_quote(resolved_ticker)
                if stale:
                    quotes[symbol] = {
                        "last": stale.get("last"),
                        "change_pct": stale.get("change_pct"),
                        "shock": None,
                        "risk": None,
                        "stale": True
                    }
                else:
                    quotes[symbol] = {
                        "last": 0.0,
                        "change_pct": 0.0,
                        "shock": None,
                        "risk": None,
                        "stale": True
                    }
            
            # Schedule background refresh if needed (non-blocking)
            _data_provider_service.schedule_refresh(resolved_ticker)
        
        # Broadcast to each client at their cadence
        now_ms = int(time.time() * 1000)
        message = {
            "t": now_ms,
            "quotes": quotes
        }
        message_json = json.dumps(message)
        
        disconnected = []
        for websocket, conn_data in self.connections.items():
            try:
                await websocket.send_text(message_json)
            except Exception:
                disconnected.append(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            self.disconnect(ws)


# Global broadcaster instance
broadcaster = MarketBroadcaster()


async def market_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time market data.
    
    Client can subscribe:
    {
        "type": "subscribe",
        "symbols": ["AAPL", "MSFT"],
        "cadence_ms": 250
    }
    
    Server pushes:
    {
        "t": 1234567890,
        "quotes": {
            "AAPL": {"last": 150.0, "change_pct": 1.5, "shock": null, "risk": null, "stale": false},
            "MSFT": {"last": 300.0, "change_pct": -0.5, "shock": null, "risk": null, "stale": false}
        }
    }
    """
    await broadcaster.connect(websocket)
    
    # Start broadcast loop for this client
    last_broadcast = 0
    cadence_ms = 250
    
    try:
        while True:
            # Handle incoming messages (subscriptions)
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                try:
                    message = json.loads(data)
                    await broadcaster.handle_subscription(websocket, message)
                    if websocket in broadcaster.connections:
                        cadence_ms = broadcaster.connections[websocket]["cadence_ms"]
                except json.JSONDecodeError:
                    logger.debug(f"Invalid JSON from client: {data}")
            except asyncio.TimeoutError:
                pass
            
            # Broadcast at cadence
            now_ms = int(time.time() * 1000)
            if now_ms - last_broadcast >= cadence_ms:
                await broadcaster.broadcast_quotes()
                last_broadcast = now_ms
            
            # Small sleep to prevent tight loop
            await asyncio.sleep(0.01)
    
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
    except Exception as e:
        logger.error(f"Market WS error: {e}", exc_info=True)
        broadcaster.disconnect(websocket)
