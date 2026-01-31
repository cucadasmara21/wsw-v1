"""
Technical metrics computation from price bars
Computes risk, shock, trend, volatility and packs into meta32
"""
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def compute_returns(prices: List[float]) -> np.ndarray:
    """Compute log returns from price series"""
    if len(prices) < 2:
        return np.array([])
    prices_arr = np.array(prices)
    returns = np.diff(np.log(prices_arr + 1e-10))
    return returns


def compute_volatility(returns: np.ndarray, window: int = 20) -> float:
    """Compute rolling volatility (annualized)"""
    if len(returns) < window:
        return 0.0
    recent = returns[-window:]
    vol = np.std(recent) * np.sqrt(252)  # Annualized
    return float(np.clip(vol, 0.0, 2.0))


def compute_shock(returns: np.ndarray, threshold: float = 0.05) -> float:
    """Compute shock intensity (recent extreme moves)"""
    if len(returns) < 5:
        return 0.0
    recent = np.abs(returns[-5:])
    max_move = np.max(recent)
    shock = min(max_move / threshold, 1.0)
    return float(shock)


def compute_trend(returns: np.ndarray, window: int = 10) -> int:
    """
    Compute trend: 0=flat, 1=bull, 2=bear
    """
    if len(returns) < window:
        return 0
    recent = returns[-window:]
    avg_return = np.mean(recent)
    if avg_return > 0.001:
        return 1  # bull
    elif avg_return < -0.001:
        return 2  # bear
    return 0  # flat


def compute_risk_score(returns: np.ndarray, volatility: float) -> float:
    """Compute normalized risk score [0,1]"""
    if len(returns) < 5:
        return 0.5
    recent_vol = np.std(returns[-20:]) * np.sqrt(252) if len(returns) >= 20 else volatility
    risk = min(recent_vol / 0.5, 1.0)  # Normalize by 50% vol
    return float(np.clip(risk, 0.0, 1.0))


def pack_meta32(risk01: float, shock01: float, trend: int, volatility01: float, temporal: int = 0) -> int:
    """
    Pack metrics into 32-bit meta32:
    - risk: bits 0-6 (7 bits, 0-127)
    - shock: bits 7-13 (7 bits, 0-127)
    - trend: bits 14-15 (2 bits: 00=flat, 01=bull, 10=bear)
    - volatility: bits 16-21 (6 bits, 0-63)
    - temporal: bits 22-31 (10 bits, 0-1023)
    """
    risk8 = int(np.clip(risk01 * 127.0, 0, 127))
    shock8 = int(np.clip(shock01 * 127.0, 0, 127))
    trend2 = int(np.clip(trend, 0, 3)) & 0x3
    vol6 = int(np.clip(volatility01 * 63.0, 0, 63))
    temporal10 = int(np.clip(temporal, 0, 1023)) & 0x3FF
    
    meta32 = (
        (risk8 & 0x7F) |
        ((shock8 & 0x7F) << 7) |
        ((trend2 & 0x3) << 14) |
        ((vol6 & 0x3F) << 16) |
        ((temporal10 & 0x3FF) << 22)
    )
    
    return meta32 & 0xFFFFFFFF


def compute_metrics_from_bars(bars: List[Dict], asset_id: int) -> Optional[Dict]:
    """
    Compute metrics from price bars and pack into meta32.
    
    Args:
        bars: List of dicts with 'close', 'open', 'high', 'low', 'volume'
        asset_id: Asset ID for logging
    
    Returns:
        Dict with: risk01, shock01, trend, volatility01, meta32
    """
    if not bars or len(bars) < 5:
        logger.warning(f"Asset {asset_id}: insufficient bars ({len(bars)})")
        return None
    
    closes = [float(b['close']) for b in bars if b.get('close')]
    if len(closes) < 5:
        return None
    
    returns = compute_returns(closes)
    if len(returns) < 5:
        return None
    
    volatility = compute_volatility(returns)
    volatility01 = min(volatility / 0.5, 1.0)
    
    shock01 = compute_shock(returns)
    trend = compute_trend(returns)
    risk01 = compute_risk_score(returns, volatility)
    
    temporal = hash(str(asset_id)) % 1024
    
    meta32 = pack_meta32(risk01, shock01, trend, volatility01, temporal)
    
    return {
        'risk01': risk01,
        'shock01': shock01,
        'trend': trend,
        'volatility01': volatility01,
        'meta32': meta32
    }
