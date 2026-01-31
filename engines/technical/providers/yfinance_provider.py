"""
yfinance provider for equity/ETF data ingestion
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import numpy as np

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
    import pandas as pd
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not available. Install: pip install yfinance")


def fetch_ohlcv(symbol: str, interval: str = "1d", limit: int = 90) -> List[Dict]:
    """
    Fetch OHLCV data for a symbol.
    
    Args:
        symbol: Asset symbol (e.g., "AAPL")
        interval: yfinance interval ("1d", "1h", etc.)
        limit: Number of days to fetch
    
    Returns:
        List of dicts with keys: ts, open, high, low, close, volume
    """
    if not YFINANCE_AVAILABLE:
        raise ImportError("yfinance not installed")
    
    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=limit)
        
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date, interval=interval, auto_adjust=True)
        
        if df.empty:
            return []
        
        bars = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, 'to_pydatetime') else datetime.fromtimestamp(idx.timestamp())
            bars.append({
                'ts': ts,
                'open': float(row['Open']) if pd.notna(row['Open']) else None,
                'high': float(row['High']) if pd.notna(row['High']) else None,
                'low': float(row['Low']) if pd.notna(row['Low']) else None,
                'close': float(row['Close']) if pd.notna(row['Close']) else None,
                'volume': int(row['Volume']) if pd.notna(row['Volume']) else None
            })
        
        return bars
    except Exception as e:
        logger.error(f"yfinance fetch failed for {symbol}: {e}")
        return []


def is_crypto_symbol(symbol: str) -> bool:
    """Check if symbol is crypto (simple heuristic)"""
    return symbol.endswith('-USD') or symbol.endswith('USDT') or symbol in ['BTC', 'ETH', 'SOL']
