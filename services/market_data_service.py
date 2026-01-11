"""Market data service: fetch and persist historical price bars."""
from __future__ import annotations

from typing import List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.orm import Session

from models import PriceBar


def fetch_history(symbol: str, period: str = "6mo", interval: str = "1d") -> List[Dict[str, Any]]:
    """
    Fetch historical OHLCV data using yfinance.

    Returns a list of dicts with keys: ts, open, high, low, close, volume, source.
    Raises RuntimeError if yfinance/pandas are not available.
    """
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover - network path mocked in tests
        raise RuntimeError("yfinance not installed. Install requirements-analytics.txt") from exc

    df = yf.download(symbol, period=period, interval=interval, progress=False)
    if df is None or len(df) == 0:
        return []

    if hasattr(df, "reset_index"):
        df = df.reset_index()

    bars: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ts_val = row.get("Datetime") or row.get("Date") or row.get("index")
        if ts_val is None:
            continue
        # yfinance returns pandas Timestamp; ensure python datetime
        ts = ts_val.to_pydatetime() if hasattr(ts_val, "to_pydatetime") else ts_val
        bars.append({
            "ts": ts,
            "open": float(row.get("Open", row.get("open", 0)) or 0),
            "high": float(row.get("High", row.get("high", 0)) or 0),
            "low": float(row.get("Low", row.get("low", 0)) or 0),
            "close": float(row.get("Close", row.get("close", 0)) or 0),
            "volume": int(row.get("Volume", row.get("volume", 0)) or 0),
            "source": "yfinance",
        })
    return bars


def upsert_price_bars(db: Session, symbol: str, bars: List[Dict[str, Any]]) -> Tuple[int, int]:
    """
    Insert new PriceBar records idempotently.

    Args:
        db: Session
        symbol: ticker symbol
        bars: list of dicts with ts/open/high/low/close/volume/source
    Returns:
        (rows_inserted, rows_total_for_symbol)
    """
    inserted = 0
    for bar in bars:
        ts = bar["ts"]
        exists = db.query(PriceBar).filter(PriceBar.symbol == symbol, PriceBar.ts == ts).first()
        if exists:
            continue
        db.add(PriceBar(
            symbol=symbol,
            ts=ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts)),
            open=bar.get("open"),
            high=bar.get("high"),
            low=bar.get("low"),
            close=bar.get("close"),
            volume=bar.get("volume"),
            source=bar.get("source", "yfinance")
        ))
        inserted += 1
    db.commit()
    total = db.query(PriceBar).filter(PriceBar.symbol == symbol).count()
    return inserted, total
*** End of File
