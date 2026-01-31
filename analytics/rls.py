"""
Recursive Least Squares (RLS) trend detector.
Produces trend2: 0=flat, 1=bull, 2=bear based on RLS slope.
"""

import numpy as np
from typing import Dict, Tuple, Optional


class RLSTrendDetector:
    """
    RLS-based trend detector using exponential forgetting.
    Outputs trend2: 0 (flat), 1 (bull), 2 (bear).
    """
    
    def __init__(self, forgetting_factor: float = 0.95, min_samples: int = 5):
        """
        Args:
            forgetting_factor: Exponential forgetting (0.9-0.99, higher = more memory)
            min_samples: Minimum samples before detecting trend
        """
        self.lambda_ = forgetting_factor
        self.min_samples = min_samples
        # Per-asset state: (P, theta, count, last_price)
        # P: covariance matrix (scalar for 1D), theta: slope estimate, count: sample count
        self.state: Dict[int, Tuple[float, float, int, Optional[float]]] = {}
    
    def update(self, asset_id: int, price: float, timestamp: Optional[float] = None) -> int:
        """
        Update RLS state and return trend2.
        
        Args:
            asset_id: Asset identifier
            price: Current price
            timestamp: Optional timestamp (uses count if None)
            
        Returns:
            trend2: 0 (flat), 1 (bull), 2 (bear)
        """
        if asset_id not in self.state:
            # Initialize: P=1.0, theta=0.0, count=0, last_price=price
            self.state[asset_id] = (1.0, 0.0, 0, price)
            return 0  # Flat on first observation
        
        P, theta, count, last_price = self.state[asset_id]
        
        if last_price is None:
            self.state[asset_id] = (P, theta, count, price)
            return 0
        
        # Use time delta or count as regressor
        if timestamp is not None:
            # For now, use count as proxy (can be enhanced with real timestamps)
            x = float(count + 1)
        else:
            x = float(count + 1)
        
        # Price change
        y = price - last_price
        
        # RLS update (simplified 1D case)
        # Innovation: y - theta * x
        innovation = y - theta * x
        
        # Kalman gain
        K = P * x / (self.lambda_ + P * x * x)
        
        # Update theta (slope estimate)
        theta_new = theta + K * innovation
        
        # Update covariance
        P_new = (1.0 / self.lambda_) * (P - K * x * P)
        
        # Ensure P stays positive
        P_new = max(0.001, P_new)
        
        # Determine trend based on slope
        trend2 = 0  # flat
        if count >= self.min_samples:
            # Normalize slope by price to get relative change rate
            if last_price > 0:
                relative_slope = theta_new / last_price
                # Thresholds: > 0.0001 = bull, < -0.0001 = bear
                if relative_slope > 0.0001:
                    trend2 = 1  # bull
                elif relative_slope < -0.0001:
                    trend2 = 2  # bear
                # else: trend2 = 0 (flat)
        
        # Update state
        self.state[asset_id] = (P_new, theta_new, count + 1, price)
        
        return trend2
    
    def reset(self, asset_id: int):
        """Reset state for an asset."""
        if asset_id in self.state:
            del self.state[asset_id]
    
    def reset_all(self):
        """Reset all state."""
        self.state.clear()
