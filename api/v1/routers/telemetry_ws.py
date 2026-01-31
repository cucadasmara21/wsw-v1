"""
Telemetry WebSocket: Real-time heartbeat and system pulse
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from datetime import datetime
import asyncio
import json
import time
from typing import Dict, Optional

from database import engine
from sqlalchemy import text

router = APIRouter()


class TelemetryBroadcaster:
    """Manages WebSocket connections and broadcasts telemetry"""
    
    def __init__(self):
        self.connections: list[WebSocket] = []
        self.last_heartbeat: Optional[float] = None
        self.last_error: Optional[str] = None
    
    async def connect(self, websocket: WebSocket):
        """Add a new WebSocket connection"""
        await websocket.accept()
        self.connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.connections:
            self.connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        if not self.connections:
            return
        
        message_json = json.dumps(message)
        disconnected = []
        
        for connection in self.connections:
            try:
                await connection.send_text(message_json)
            except Exception:
                disconnected.append(connection)
        
        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)
    
    async def send_heartbeat(self):
        """Send heartbeat message"""
        try:
            # Get system metrics
            bars_inserted = await self._get_bars_inserted()
            sim_latency_ms = await self._get_sim_latency()
            taxonomy_state = await self._get_taxonomy_state()
            points_count = await self._get_points_count()
            
            heartbeat_age_s = 0.0
            if self.last_heartbeat:
                heartbeat_age_s = time.time() - self.last_heartbeat
            
            self.last_heartbeat = time.time()
            
            # Get prefix bucket telemetry stats (if available)
            prefix_telemetry = await self._get_prefix_telemetry()
            
            message = {
                "type": "heartbeat",
                "ts": datetime.utcnow().isoformat(),
                "bars_inserted": bars_inserted,
                "sim_latency_ms": sim_latency_ms,
                "taxonomy_state": taxonomy_state,
                "points_count": points_count,
                "assets_count": points_count,
                "mode": "sovereign",
                "heartbeat_age_s": round(heartbeat_age_s, 2),
                "last_error": self.last_error
            }
            
            # Append prefix bucket stats (non-breaking addition)
            if prefix_telemetry:
                message.update(prefix_telemetry)
            
            await self.broadcast(message)
        except Exception as e:
            self.last_error = str(e)
            # Still send heartbeat even on error (degrade, don't freeze)
            await self.broadcast({
                "type": "heartbeat",
                "ts": datetime.utcnow().isoformat(),
                "error": str(e),
                "heartbeat_age_s": 0.0
            })
    
    async def _get_bars_inserted(self) -> int:
        """Get count of price bars inserted (last 24h)"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    SELECT COUNT(*) as cnt
                    FROM prices
                    WHERE time >= datetime('now', '-1 day')
                """))
                row = result.fetchone()
                return row[0] if row else 0
        except:
            return 0
    
    async def _get_sim_latency(self) -> Optional[float]:
        """Get latest simulation latency (mock, would come from metrics store)"""
        # In production, this would query a metrics store
        return None
    
    async def _get_taxonomy_state(self) -> str:
        """Get taxonomy engine state"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM assets WHERE is_active = 1"))
                count = result.fetchone()[0]
                return f"active ({count} assets)"
        except:
            return "unknown"
    
    async def _get_points_count(self) -> int:
        """Get count of active points for rendering"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM assets WHERE is_active = 1"))
                return result.fetchone()[0] or 0
        except:
            return 0
    
    async def _get_prefix_telemetry(self) -> Optional[Dict]:
        """Get prefix bucket index telemetry stats (if causal engine is active)"""
        try:
            # Try to import and get stats from prefix bucket index
            # This is optional - if not available, return None (non-breaking)
            from engines.prefix_bucket_index import PrefixBucketIndex
            # In production, this would query a cached index instance
            # For now, return mock stats structure
            return {
                "prefix_avg_ms": None,  # Would be populated by actual propagation calls
                "prefix_affected_count": None,
                "prefix_len": None
            }
        except:
            return None


# Global broadcaster instance
broadcaster = TelemetryBroadcaster()


@router.websocket("/ws/v1/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time telemetry.
    
    Sends heartbeat every 1 second:
    {
        "type": "heartbeat",
        "ts": "2026-01-16T00:00:00Z",
        "bars_inserted": 1234,
        "sim_latency_ms": 145.2,
        "taxonomy_state": "active (1000 assets)",
        "mode": "sovereign",
        "heartbeat_age_s": 1.0,
        "last_error": null
    }
    """
    await broadcaster.connect(websocket)
    
    try:
        # Send initial heartbeat
        await broadcaster.send_heartbeat()
        
        # Keep connection alive and send heartbeats
        while True:
            await asyncio.sleep(1.0)  # 1 second interval
            await broadcaster.send_heartbeat()
    
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
    except Exception as e:
        broadcaster.last_error = str(e)
        broadcaster.disconnect(websocket)
