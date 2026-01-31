"""
CoinGecko provider for crypto data ingestion
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import requests

logger = logging.getLogger(__name__)

COINGECKO_API = "https://api.coingecko.com/api/v3"


def fetch_ohlcv(symbol: str, interval: str = "1d", limit: int = 90) -> List[Dict]:
    """
    Fetch OHLCV data for a crypto symbol.
    
    Args:
        symbol: Crypto symbol (e.g., "bitcoin", "ethereum")
        interval: Not used (always daily)
        limit: Number of days to fetch
    
    Returns:
        List of dicts with keys: ts, open, high, low, close, volume
    """
    try:
        symbol_lower = symbol.lower().replace('-usd', '').replace('-usdt', '')
        
        url = f"{COINGECKO_API}/coins/{symbol_lower}/ohlc"
        params = {"vs_currency": "usd", "days": limit}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        bars = []
        for row in data:
            ts = datetime.fromtimestamp(row[0] / 1000)
            bars.append({
                'ts': ts,
                'open': float(row[1]),
                'high': float(row[2]),
                'low': float(row[3]),
                'close': float(row[4]),
                'volume': None
            })
        
        return bars
    except Exception as e:
        logger.error(f"CoinGecko fetch failed for {symbol}: {e}")
        return []
