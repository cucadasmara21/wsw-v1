"""
CUSUM (Cumulative Sum) detector for shock detection.
Produces shock8 score (0-255) based on cumulative deviation from mean.
"""

import numpy as np
from typing import Dict, Tuple


class CUSUMDetector:
    """
    CUSUM detector for detecting sudden changes in price returns.
    Outputs shock8 (0-255) where higher values indicate stronger shock signals.
    """
    
    def __init__(self, threshold: float = 0.02, drift: float = 0.001):
        """
        Args:
            threshold: Detection threshold (typical: 0.01-0.05)
            drift: Expected drift per period (typical: 0.0001-0.001)
        """
        self.threshold = threshold
        self.drift = drift
        # Per-asset state: (S_plus, S_minus, mean, count)
        self.state: Dict[int, Tuple[float, float, float, int]] = {}
    
    def update(self, asset_id: int, return_value: float) -> int:
        """
        Update CUSUM state for an asset and return shock8 score.
        
        Args:
            asset_id: Asset identifier
            return_value: Price return (log or simple)
            
        Returns:
            shock8: Integer 0-255 representing shock intensity
        """
        if asset_id not in self.state:
            # Initialize: S_plus=0, S_minus=0, mean=return, count=1
            self.state[asset_id] = (0.0, 0.0, return_value, 1)
            return 0  # No shock on first observation
        
        S_plus, S_minus, mean, count = self.state[asset_id]
        
        # Update running mean (exponential moving average)
        alpha = 1.0 / min(count, 100)  # Decay factor
        new_mean = (1.0 - alpha) * mean + alpha * return_value
        
        # Compute deviation from mean
        deviation = return_value - new_mean
        
        # Update CUSUM statistics
        # S_plus: cumulative positive deviations
        # S_minus: cumulative negative deviations
        S_plus_new = max(0.0, S_plus + deviation - self.drift)
        S_minus_new = max(0.0, S_minus - deviation - self.drift)
        
        # Detect shock if either statistic exceeds threshold
        shock_magnitude = max(S_plus_new, S_minus_new)
        
        # Normalize to [0, 1] using tanh saturation
        # Scale by threshold: shock_magnitude / (threshold * 2) -> [0, 1]
        normalized = np.tanh(shock_magnitude / (self.threshold * 2.0))
        
        # Convert to 0-255
        shock8 = int(np.clip(normalized * 255.0, 0, 255))
        
        # Update state
        self.state[asset_id] = (S_plus_new, S_minus_new, new_mean, count + 1)
        
        return shock8
    
    def reset(self, asset_id: int):
        """Reset state for an asset."""
        if asset_id in self.state:
            del self.state[asset_id]
    
    def reset_all(self):
        """Reset all state."""
        self.state.clear()
