"""
WebSocket endpoint for real-time universe updates.
Sends binary diff frames: [u32 count][repeated: u32 index, u32 attr, u32 meta]
"""

import struct
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set

from services.points_buffer_service import get_points_buffer_service

logger = logging.getLogger(__name__)
router = APIRouter()

# Track active WebSocket connections
_active_connections: Set[WebSocket] = set()

# Binary frame format:
# [u32 count][repeated: u32 index, u32 attr, u32 meta]
# For now, we only update meta32 (attr = taxonomy32, unchanged)
_DIFF_STRUCT = struct.Struct("<I")  # count
_UPDATE_STRUCT = struct.Struct("<III")  # index, attr, meta32


async def broadcast_diff(updates: dict[int, int]):
    """
    Broadcast diff updates to all connected WebSocket clients.
    
    Args:
        updates: Dict mapping index -> meta32
    """
    if not updates or not _active_connections:
        return
    
    # Build binary frame
    count = len(updates)
    frame = bytearray()
    frame.extend(_DIFF_STRUCT.pack(count))
    
    # Get buffer service to read taxonomy32 (attr) for each index
    buffer_service = get_points_buffer_service()
    
    for index, meta32 in updates.items():
        # Read current taxonomy32 from buffer (attr field)
        # For now, we'll use 0 as placeholder (can be enhanced to read actual attr)
        attr = 0  # TODO: read actual taxonomy32 from buffer if needed
        frame.extend(_UPDATE_STRUCT.pack(index, attr, meta32))
    
    # Send to all connected clients
    disconnected = set()
    for ws in _active_connections:
        try:
            await ws.send_bytes(bytes(frame))
        except Exception as e:
            logger.debug(f"Failed to send to WebSocket client: {e}")
            disconnected.add(ws)
    
    # Remove disconnected clients
    for ws in disconnected:
        _active_connections.discard(ws)


@router.websocket("/ws/universe")
async def websocket_universe(websocket: WebSocket):
    """
    WebSocket endpoint for real-time universe updates.
    
    Protocol:
    - On connect: sends hello message with build_tag
    - On each tick: sends binary diff frames with updated indices and meta32
    """
    await websocket.accept()
    _active_connections.add(websocket)
    
    logger.info(f"WebSocket client connected. Total connections: {len(_active_connections)}")
    
    # Send hello message
    try:
        hello = {
            "type": "hello",
            "build_tag": "TITAN_V8_ANALYTICS",
            "message": "Connected to Titan Universe WebSocket"
        }
        await websocket.send_json(hello)
    except Exception as e:
        logger.warning(f"Failed to send hello: {e}")
    
    try:
        # Keep connection alive and wait for messages (client can send ping/pong)
        while True:
            # Wait for any message (ping/pong or close)
            data = await websocket.receive()
            
            if data.get("type") == "websocket.disconnect":
                break
            
            # Echo ping as pong (optional)
            if data.get("type") == "websocket.receive":
                msg = data.get("text") or data.get("bytes")
                if msg == "ping":
                    await websocket.send_text("pong")
    
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        _active_connections.discard(websocket)
        logger.info(f"WebSocket client removed. Total connections: {len(_active_connections)}")


def get_active_connection_count() -> int:
    """Get number of active WebSocket connections."""
    return len(_active_connections)
