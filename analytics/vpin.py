"""
VPIN (Volume-synchronized Probability of Informed Trading) calculator.
Produces risk8 and vital6 proxies based on volume imbalance.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque


class VPINCalculator:
    """
    VPIN calculator for risk and vitality metrics.
    Outputs risk8 (0-255) and vital6 (0-63) based on volume flow imbalance.
    """
    
    def __init__(self, window_size: int = 50, bucket_count: int = 1):
        """
        Args:
            window_size: Number of buckets to consider
            bucket_count: Number of trades per bucket (simplified: 1 for now)
        """
        self.window_size = window_size
        self.bucket_count = bucket_count
        # Per-asset state: deque of (buy_volume, sell_volume, total_volume)
        self.state: Dict[int, deque] = {}
    
    def update(self, asset_id: int, price: float, volume: float = 1.0, 
               prev_price: Optional[float] = None) -> Tuple[int, int]:
        """
        Update VPIN state and return risk8, vital6.
        
        Args:
            asset_id: Asset identifier
            price: Current price
            volume: Trade volume (default 1.0 if not available)
            prev_price: Previous price (for buy/sell classification)
            
        Returns:
            (risk8, vital6): Tuple of integers 0-255 and 0-63
        """
        if asset_id not in self.state:
            self.state[asset_id] = deque(maxlen=self.window_size)
        
        bucket = self.state[asset_id]
        
        # Classify volume as buy or sell based on price change
        if prev_price is not None:
            if price > prev_price:
                buy_vol = volume
                sell_vol = 0.0
            elif price < prev_price:
                buy_vol = 0.0
                sell_vol = volume
            else:
                # Flat: split evenly
                buy_vol = volume * 0.5
                sell_vol = volume * 0.5
        else:
            # First observation: assume neutral
            buy_vol = volume * 0.5
            sell_vol = volume * 0.5
        
        bucket.append((buy_vol, sell_vol, volume))
        
        if len(bucket) < 2:
            return (128, 32)  # Neutral values
        
        # Compute VPIN: average volume imbalance over window
        total_buy = sum(b[0] for b in bucket)
        total_sell = sum(b[1] for b in bucket)
        total_vol = sum(b[2] for b in bucket)
        
        # P-02: Clamp liquidity denominator before reciprocal (no overflow)
        KAPPA_MIN = 1e-3
        total_vol = max(total_vol, KAPPA_MIN)
        
        # Volume imbalance ratio
        imbalance = abs(total_buy - total_sell) / total_vol
        
        # VPIN is the expected value of imbalance
        vpin = float(np.clip(imbalance, 0.0, 1.0))  # P-02: E clamp [0,1] for VPIN
        
        # Risk8: higher VPIN = higher risk (0-255)
        # Map VPIN [0, 1] -> risk8 [0, 255] with saturation
        risk8 = int(np.clip(vpin * 255.0, 0, 255))
        
        # Vital6: inverse of risk (liquidity proxy), normalized to 0-63
        # Higher liquidity (lower VPIN) = higher vitality
        vitality = 1.0 - vpin
        vital6 = int(np.clip(vitality * 63.0, 0, 63))
        
        return (risk8, vital6)
    
    def reset(self, asset_id: int):
        """Reset state for an asset."""
        if asset_id in self.state:
            del self.state[asset_id]
    
    def reset_all(self):
        """Reset all state."""
        self.state.clear()
