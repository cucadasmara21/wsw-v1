"""
Risk Engine v1

Computes risk metrics for assets:
- risk_vector: components (volatility, max_drawdown, momentum, liquidity, centrality)
- CRI (Composite Risk Index 0-100): weighted combination of risk components

This module is INDEPENDENT of risk_snapshots and provides real-time computation.
"""

import numpy as np
from typing import Optional, Dict, Any, List


def _safe_stdev(returns: np.ndarray) -> float:
    """Safely compute standard deviation, avoiding empty/single-element arrays."""
    if len(returns) < 2:
        return 0.0
    return float(np.std(returns, ddof=1))


def _safe_max_drawdown(prices: np.ndarray) -> float:
    """
    Compute maximum drawdown (0..1).
    Returns 0 if prices are invalid or monotonically increasing.
    """
    if len(prices) < 2:
        return 0.0
    
    cumulative_max = np.maximum.accumulate(prices)
    drawdowns = (prices - cumulative_max) / np.maximum(cumulative_max, 1e-10)
    mdd = float(np.min(drawdowns))
    return max(0.0, -mdd)  # Ensure non-negative


def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value to [min_val, max_val]."""
    return float(max(min_val, min(max_val, value)))


def compute_risk_vector(
    prices: list[float],
    volumes: Optional[list[float]] = None,
    lookback_days: int = 90,
) -> Dict[str, Any]:
    """
    Compute risk vector components for an asset.
    
    Args:
        prices: list of closing prices (most recent last)
        volumes: list of trading volumes (optional)
        lookback_days: number of historical days to consider
    
    Returns:
        dict with keys:
        - volatility (30d annualized): 0..1
        - max_drawdown (90d): 0..1
        - momentum_30d: -1..1 (negative = higher risk)
        - liquidity: 0..1 (0 = illiquid, 1 = liquid)
        - centrality: 0..1 (neutral=0.5 if not computed)
        - insufficient_data: bool
    """
    
    vector = {
        "volatility": 0.0,
        "max_drawdown": 0.0,
        "momentum_30d": 0.0,
        "liquidity": 0.5,  # neutral
        "centrality": 0.5,  # neutral
        "insufficient_data": False,
    }
    
    # Validate input
    if not prices or len(prices) < 2:
        vector["insufficient_data"] = True
        return vector
    
    prices_arr = np.array(prices, dtype=float)
    
    # Remove NaNs
    prices_arr = prices_arr[~np.isnan(prices_arr)]
    if len(prices_arr) < 2:
        vector["insufficient_data"] = True
        return vector
    
    # 1. Volatility (30-day window, annualized)
    if len(prices_arr) >= 30:
        prices_30d = prices_arr[-30:]
        returns_30d = np.diff(prices_30d) / prices_30d[:-1]
        vol_30d = _safe_stdev(returns_30d)
        # Annualize and normalize to 0..1 (assumes typical daily vol 1-3%)
        vol_annual = vol_30d * np.sqrt(252)
        vector["volatility"] = _clamp(vol_annual / 0.5, 0, 1)  # 0.5 = 50% annual vol = max
    else:
        # Use all available data
        returns = np.diff(prices_arr) / prices_arr[:-1]
        vol = _safe_stdev(returns)
        vector["volatility"] = _clamp(vol / 0.1, 0, 1)
    
    # 2. Max Drawdown (90-day, or all available)
    vector["max_drawdown"] = _safe_max_drawdown(prices_arr)
    
    # 3. Momentum (30-day return)
    if len(prices_arr) >= 30:
        momentum = (prices_arr[-1] - prices_arr[-30]) / prices_arr[-30]
    else:
        momentum = (prices_arr[-1] - prices_arr[0]) / prices_arr[0]
    
    # Normalize momentum to -1..1: positive momentum reduces risk (shift to -0.5..0.5)
    momentum_normalized = _clamp(momentum / 0.3, -1, 1)  # 30% = max shift
    # Convert to risk component: negative momentum = high risk
    vector["momentum_30d"] = max(0.0, -momentum_normalized * 0.5 + 0.5)  # 0.5 = neutral
    
    # 4. Liquidity (if volumes provided)
    if volumes and len(volumes) >= 10:
        vol_arr = np.array(volumes, dtype=float)
        vol_arr = vol_arr[~np.isnan(vol_arr)]
        if len(vol_arr) > 0:
            # Simple: if avg volume > 0 and recent is non-zero
            avg_vol = np.mean(vol_arr[-10:])
            if avg_vol > 0:
                vector["liquidity"] = _clamp(np.log(avg_vol + 1) / np.log(1e6), 0, 1)
            else:
                vector["liquidity"] = 0.1  # very illiquid
    
    # 5. Centrality: neutral (0.5) unless explicitly computed elsewhere
    # This would come from correlation to market or group; for now, neutral
    vector["centrality"] = 0.5
    
    return vector


def compute_cri(risk_vector: Dict[str, Any]) -> Optional[float]:
    """
    Compute Composite Risk Index (CRI) from risk_vector.
    
    Formula:
    CRI = 100 * clamp(
        0.30 * volatility
        + 0.30 * max_drawdown
        + 0.20 * (1 - liquidity)  # illiquidity is risk
        + 0.10 * momentum_30d
        + 0.10 * centrality
    , 0..1)
    
    Args:
        risk_vector: output from compute_risk_vector()
    
    Returns:
        CRI (0..100) or None if insufficient data
    """
    
    if risk_vector.get("insufficient_data", False):
        return None
    
    components = risk_vector
    
    # Weighted combination
    cri_normalized = (
        0.30 * components.get("volatility", 0.0)
        + 0.30 * components.get("max_drawdown", 0.0)
        + 0.20 * (1.0 - components.get("liquidity", 0.5))  # illiquidity is risk
        + 0.10 * components.get("momentum_30d", 0.5)
        + 0.10 * components.get("centrality", 0.5)
    )
    
    cri_normalized = _clamp(cri_normalized, 0.0, 1.0)
    cri = float(cri_normalized * 100.0)
    
    return cri
