"""
FRED provider stub (requires API key)
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

FRED_AVAILABLE = False

try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    logger.warning("fredapi not available. Install: pip install fredapi")


def fetch_ohlcv(symbol: str, interval: str = "1d", limit: int = 90) -> List[Dict]:
    """
    Stub: FRED provider requires API key configuration.
    """
    if not FRED_AVAILABLE:
        raise ImportError("fredapi not installed")
    
    logger.warning(f"FRED provider not configured (requires API key). Symbol: {symbol}")
    return []
