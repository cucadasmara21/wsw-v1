"""
Thread-safe points.bin buffer service.
Route A: manages a shared Vertex28 buffer for /api/universe/points.bin and WebSocket updates.
"""

import struct
import threading
import logging
from typing import Optional, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from services.vertex28 import VERTEX28_STRIDE, pack_vertex28, unpack_vertex28

logger = logging.getLogger(__name__)

_VERTEX28_STRUCT = struct.Struct("<IIfffff")
assert _VERTEX28_STRUCT.size == VERTEX28_STRIDE

class PointsBufferService:
    """
    Thread-safe service for managing a Vertex28 points buffer.
    Supports in-place updates of meta32 field without full rebuild.
    """
    
    def __init__(self):
        self.lock = threading.RLock()
        self.buffer: Optional[bytearray] = None
        self.asset_count = 0
        self.symbol_to_index: Dict[str, int] = {}
        self.index_to_asset_id: Dict[int, int] = {}
        self._initialized = False
    
    def initialize(self, db: Session, limit: int = 100000):
        """
        Initialize buffer from database.
        Must be called before any updates.
        """
        with self.lock:
            try:
                rows = db.execute(
                    text("""
                        SELECT
                          symbol,
                          vertex_buffer
                        FROM public.universe_assets
                        ORDER BY morton_code ASC
                        LIMIT :limit
                    """),
                    {"limit": int(limit)},
                ).fetchall()
                
                n = len(rows)
                if n == 0:
                    logger.warning("No assets found for points buffer")
                    return False
                
                # Allocate buffer
                buf = bytearray(n * VERTEX28_STRIDE)
                
                self.symbol_to_index.clear()
                self.index_to_asset_id.clear()
                
                for idx, r in enumerate(rows):
                    symbol = str(r.symbol) if r.symbol else f"ASSET-{idx}"
                    vb = bytes(r.vertex_buffer) if r.vertex_buffer is not None else b""
                    if len(vb) != VERTEX28_STRIDE:
                        raise RuntimeError(f"vertex_buffer stride != 28 for symbol={symbol}")
                    buf[idx * VERTEX28_STRIDE : (idx + 1) * VERTEX28_STRIDE] = vb
                    
                    # Store mappings
                    self.symbol_to_index[symbol] = idx
                    self.index_to_asset_id[idx] = idx
                
                self.buffer = buf
                self.asset_count = n
                self._initialized = True
                
                logger.info(f"Points buffer initialized: {n} assets, {len(buf)} bytes")
                return True
                
            except Exception as e:
                logger.error(f"Failed to initialize points buffer: {e}", exc_info=True)
                return False
    
    def update_meta32(self, index: int, meta32: int) -> bool:
        """
        Update meta32 field for a single asset by index.
        
        Args:
            index: Asset index (0-based)
            meta32: New meta32 value
            
        Returns:
            True if updated, False if invalid index
        """
        if not self._initialized or self.buffer is None:
            return False
        
        if index < 0 or index >= self.asset_count:
            return False
        
        with self.lock:
            off = index * VERTEX28_STRIDE
            mv = memoryview(self.buffer)
            
            mort_u32, _, x, y, z, risk, shock = unpack_vertex28(bytes(mv[off : off + VERTEX28_STRIDE]))
            vb = pack_vertex28(mort_u32, int(meta32) & 0xFFFFFFFF, x, y, z, risk, shock)
            mv[off : off + VERTEX28_STRIDE] = vb
            
            return True
    
    def update_batch(self, updates: Dict[int, int]) -> int:
        """
        Update multiple assets' meta32 values.
        
        Args:
            updates: Dict mapping index -> meta32
            
        Returns:
            Number of successful updates
        """
        if not self._initialized or self.buffer is None:
            return 0
        
        count = 0
        with self.lock:
            mv = memoryview(self.buffer)
            for index, meta32 in updates.items():
                if 0 <= index < self.asset_count:
                    off = index * VERTEX28_STRIDE
                    mort_u32, _, x, y, z, risk, shock = unpack_vertex28(bytes(mv[off : off + VERTEX28_STRIDE]))
                    vb = pack_vertex28(mort_u32, int(meta32) & 0xFFFFFFFF, x, y, z, risk, shock)
                    mv[off : off + VERTEX28_STRIDE] = vb
                    count += 1
        
        return count
    
    def get_buffer(self) -> Optional[bytes]:
        """Get a copy of the current buffer (thread-safe)."""
        with self.lock:
            if self.buffer is None:
                return None
            return bytes(self.buffer)
    
    def get_symbol_index(self, symbol: str) -> Optional[int]:
        """Get index for a symbol."""
        return self.symbol_to_index.get(symbol)
    
    def get_asset_count(self) -> int:
        """Get current asset count."""
        return self.asset_count
    
    def is_initialized(self) -> bool:
        """Check if buffer is initialized."""
        return self._initialized


# Global singleton instance
_points_buffer_service = PointsBufferService()


def get_points_buffer_service() -> PointsBufferService:
    """Get the global points buffer service instance."""
    return _points_buffer_service
