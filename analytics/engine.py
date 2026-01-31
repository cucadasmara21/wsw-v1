"""
Analytics Engine: orchestrates CUSUM, RLS, and VPIN for real-time signal injection.
Maintains numpy arrays for efficient batch updates of 10k+ assets.
"""

import numpy as np
import struct
from typing import Dict, List, Optional, Tuple
import threading
import logging

from .cusum import CUSUMDetector
from .rls import RLSTrendDetector
from .vpin import VPINCalculator

logger = logging.getLogger(__name__)

# Meta32 bit packing (matches ingest_service.py)
def pack_meta32(shock8: int, risk8: int, trend2: int, vital6: int, macro8: int) -> int:
    """Pack signals into meta32: shock8[0-7], risk8[8-15], trend2[16-17], vital6[18-23], macro8[24-31]"""
    shock8 &= 0xFF
    risk8 &= 0xFF
    trend2 &= 0x03
    vital6 &= 0x3F
    macro8 &= 0xFF
    return shock8 | (risk8 << 8) | (trend2 << 16) | (vital6 << 18) | (macro8 << 24)


class AnalyticsEngine:
    """
    Main analytics engine that processes price updates and generates signal updates.
    Maintains efficient numpy arrays for 10k+ assets.
    """
    
    def __init__(self, asset_count: int, macro8: int = 128):
        """
        Args:
            asset_count: Number of assets to track
            macro8: Default macro signal (0-255)
        """
        self.asset_count = asset_count
        self.macro8 = macro8
        
        # Numpy arrays for efficient batch operations
        self.last_price = np.zeros(asset_count, dtype=np.float64)
        self.last_return = np.zeros(asset_count, dtype=np.float64)
        self.asset_ids = np.zeros(asset_count, dtype=np.int32)  # Maps index -> asset_id
        
        # Signal arrays (updated each tick)
        self.shock8 = np.zeros(asset_count, dtype=np.uint8)
        self.risk8 = np.zeros(asset_count, dtype=np.uint8)
        self.trend2 = np.zeros(asset_count, dtype=np.uint8)
        self.vital6 = np.zeros(asset_count, dtype=np.uint8)
        self.meta32 = np.zeros(asset_count, dtype=np.uint32)
        
        # Detectors
        self.cusum = CUSUMDetector(threshold=0.02, drift=0.001)
        self.rls = RLSTrendDetector(forgetting_factor=0.95, min_samples=5)
        self.vpin = VPINCalculator(window_size=50, bucket_count=1)
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Track which assets have been initialized
        self.initialized = np.zeros(asset_count, dtype=bool)
    
    def initialize_asset(self, index: int, asset_id: int, initial_price: float):
        """
        Initialize an asset at a given index.
        
        Args:
            index: Array index (0-based)
            asset_id: Database asset ID
            initial_price: Initial price
        """
        if index < 0 or index >= self.asset_count:
            return
        
        with self.lock:
            self.asset_ids[index] = asset_id
            self.last_price[index] = initial_price
            self.last_return[index] = 0.0
            self.initialized[index] = True
            
            # Initialize with neutral signals
            self.shock8[index] = 0
            self.risk8[index] = 128
            self.trend2[index] = 0
            self.vital6[index] = 32
            self.meta32[index] = pack_meta32(0, 128, 0, 32, self.macro8)
    
    def tick(self, prices: Dict[str, float], 
             asset_index_map: Dict[str, int],
             volumes: Optional[Dict[str, float]] = None) -> np.ndarray:
        """
        Process a tick of price updates.
        
        Args:
            prices: Dict mapping symbol -> price
            asset_index_map: Dict mapping symbol -> array index
            volumes: Optional dict mapping symbol -> volume
            
        Returns:
            Array of updated indices (uint32)
        """
        updated_indices = []
        
        with self.lock:
            for symbol, price in prices.items():
                if symbol not in asset_index_map:
                    continue
                
                index = asset_index_map[symbol]
                if not (0 <= index < self.asset_count):
                    continue
                
                if not self.initialized[index]:
                    # Initialize on first price update
                    self.initialize_asset(index, index, price)  # Use index as asset_id for now
                    continue
                
                asset_id = int(self.asset_ids[index])
                prev_price = self.last_price[index]
                
                # Compute return (log return for stability)
                if prev_price > 0:
                    return_val = np.log(price / prev_price)
                else:
                    return_val = 0.0
                
                # Update detectors
                shock8 = self.cusum.update(asset_id, return_val)
                trend2 = self.rls.update(asset_id, price)
                
                # VPIN update (use volume if available, else 1.0)
                volume = volumes.get(symbol, 1.0) if volumes else 1.0
                risk8, vital6 = self.vpin.update(asset_id, price, volume, prev_price)
                
                # Update arrays
                self.last_price[index] = price
                self.last_return[index] = return_val
                self.shock8[index] = shock8
                self.risk8[index] = risk8
                self.trend2[index] = trend2
                self.vital6[index] = vital6
                self.meta32[index] = pack_meta32(
                    shock8, risk8, trend2, vital6, self.macro8
                )
                
                updated_indices.append(index)
        
        return np.array(updated_indices, dtype=np.uint32)
    
    def get_meta32(self, index: int) -> int:
        """Get meta32 value for an asset index."""
        if 0 <= index < self.asset_count:
            return int(self.meta32[index])
        return 0
    
    def get_signals(self, index: int) -> Tuple[int, int, int, int, int]:
        """Get all signals for an asset index: (shock8, risk8, trend2, vital6, macro8)"""
        if 0 <= index < self.asset_count:
            return (
                int(self.shock8[index]),
                int(self.risk8[index]),
                int(self.trend2[index]),
                int(self.vital6[index]),
                self.macro8
            )
        return (0, 128, 0, 32, self.macro8)
    
    def update_macro8(self, macro8: int):
        """Update global macro8 signal and recompute all meta32."""
        self.macro8 = macro8 & 0xFF
        with self.lock:
            for i in range(self.asset_count):
                if self.initialized[i]:
                    self.meta32[i] = pack_meta32(
                        int(self.shock8[i]),
                        int(self.risk8[i]),
                        int(self.trend2[i]),
                        int(self.vital6[i]),
                        self.macro8
                    )
