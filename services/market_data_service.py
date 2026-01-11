"""Market data service: fetch and cache OHLCV bars."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import PriceBar
from services.cache_service import cache_service

logger = logging.getLogger(__name__)

# Optional yfinance import
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    yf = None  # type: ignore
    YFINANCE_AVAILABLE = False


MIN_BARS = 20
CACHE_TTL_SECONDS = 60
PERIOD_BY_INTERVAL = {
    "1m": "5d",
    "5m": "1mo",
    "15m": "2mo",
    "30m": "2mo",
    "1h": "6mo",
    "1d": "1y",
    "1wk": "2y",
    "1mo": "5y",
}


def _ensure_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _normalize_bars(raw_bars: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for bar in raw_bars:
        ts = _ensure_datetime(bar.get("ts") or bar.get("time") or bar.get("datetime") or bar.get("date"))
        if ts is None:
            continue
        normalized.append({
            "ts": ts.isoformat(),
            "open": float(bar.get("open")) if bar.get("open") is not None else None,
            "high": float(bar.get("high")) if bar.get("high") is not None else None,
            "low": float(bar.get("low")) if bar.get("low") is not None else None,
            "close": float(bar.get("close")),
            "volume": int(bar.get("volume")) if bar.get("volume") is not None else None,
            "source": bar.get("source") or "yfinance",
        })
    normalized.sort(key=lambda b: b["ts"])
    return normalized


def fetch_history(symbol: str, interval: str = "1d", period: str | None = None) -> List[Dict[str, Any]]:
    """Fetch historical OHLCV data using yfinance if available."""
    if not YFINANCE_AVAILABLE:
        raise RuntimeError("yfinance not installed. Install requirements-analytics.txt")

    resolved_period = period or PERIOD_BY_INTERVAL.get(interval, "1y")
    df = yf.download(symbol, period=resolved_period, interval=interval, progress=False)
    if df is None or len(df) == 0:
        return []

    if hasattr(df, "reset_index"):
        df = df.reset_index()

    bars: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        ts_val = row.get("Datetime") or row.get("Date") or row.get("index")
        if ts_val is None:
            continue
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


def get_bars(symbol: str, interval: str = "1d", limit: int = 200, use_cache: bool = True) -> List[Dict[str, Any]]:
    if limit <= 0:
        raise HTTPException(status_code=422, detail="limit must be positive")

    cache_key = f"bars:{symbol}:{interval}:{limit}"
    if use_cache:
        cached = cache_service.get_json(cache_key)
        if cached:
            return cached[:limit]

    try:
        raw_bars = fetch_history(symbol, interval=interval)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error while fetching history")
        raise HTTPException(status_code=502, detail="Failed to fetch market data") from exc

    normalized = _normalize_bars(raw_bars)
    if not normalized:
        raise HTTPException(status_code=404, detail="No price bars available for symbol")

    if len(normalized) < min(limit, MIN_BARS):
        raise HTTPException(status_code=422, detail=f"Not enough bars returned (got {len(normalized)}; need at least {min(limit, MIN_BARS)})")

    trimmed = normalized[-limit:]
    cache_service.set_json(cache_key, trimmed, ttl=CACHE_TTL_SECONDS)
    return trimmed



def persist_price_bars(db: Session, symbol: str, bars: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Best-effort idempotent persistence of bars to PriceBar."""
    inserted = 0
    for bar in bars:
        ts = _ensure_datetime(bar.get("ts"))
        if ts is None:
            continue
        exists = db.query(PriceBar).filter(PriceBar.symbol == symbol, PriceBar.ts == ts).first()
        if exists:
            continue
        db.add(PriceBar(
            symbol=symbol,
            ts=ts,
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
