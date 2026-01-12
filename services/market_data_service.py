"""Market data service: fetch and cache OHLCV bars, with data quality KPIs."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import PriceBar
from services.cache_service import cache_service
from services.rate_limiter import rate_limiter
import threading

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


class MarketKPIs:
    """Thread-safe counters for data quality KPIs."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_requests = 0
        self.cache_hits = 0
        self.stale_responses = 0
        self.provider_errors = 0
        self.rate_limited = 0
        self.confidence_sum = 0.0
        self.confidence_count = 0
        # last request hints
        self.last_was_cached = False
        self.last_was_stale = False
        self.last_source: str | None = None

    def record_request(self, *, cached: bool = False, stale: bool = False, source: str | None = None) -> None:
        with self._lock:
            self.total_requests += 1
            if cached:
                self.cache_hits += 1
            if stale:
                self.stale_responses += 1
            self.last_was_cached = cached
            self.last_was_stale = stale
            self.last_source = source

    def record_provider_error(self) -> None:
        with self._lock:
            self.provider_errors += 1

    def record_rate_limited(self) -> None:
        with self._lock:
            self.rate_limited += 1

    def add_confidence(self, value: float) -> None:
        with self._lock:
            self.confidence_sum += max(0.0, float(value))
            self.confidence_count += 1

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_requests": self.total_requests,
                "cache_hits": self.cache_hits,
                "stale_responses": self.stale_responses,
                "provider_errors": self.provider_errors,
                "rate_limited": self.rate_limited,
                "confidence_sum": self.confidence_sum,
                "confidence_count": self.confidence_count,
                "last": {
                    "cached": self.last_was_cached,
                    "stale": self.last_was_stale,
                    "source": self.last_source,
                },
            }


# Global KPIs instance
market_kpis = MarketKPIs()


def get_kpis_snapshot() -> Dict[str, Any]:
    """Return a flat, JSON-serializable snapshot of data quality KPIs."""
    k = market_kpis.get_stats()
    total = max(0, int(k.get("total_requests", 0)))
    hits = max(0, int(k.get("cache_hits", 0)))
    stale = max(0, int(k.get("stale_responses", 0)))
    conf_sum = float(k.get("confidence_sum", 0.0))
    conf_cnt = max(0, int(k.get("confidence_count", 0)))

    return {
        "total_requests": total,
        "cache_hits": hits,
        "stale_responses": stale,
        "provider_errors": max(0, int(k.get("provider_errors", 0))),
        "rate_limited": max(0, int(k.get("rate_limited", 0))),
        "cached_percent": round(((hits / total) * 100) if total > 0 else 0.0, 2),
        "stale_percent": round(((stale / total) * 100) if total > 0 else 0.0, 2),
        "avg_confidence": round((conf_sum / conf_cnt) if conf_cnt > 0 else 0.0, 4),
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
    cached_hit = False
    if use_cache:
        cached = cache_service.get_json(cache_key)
        if cached:
            cached_hit = True
            # record request as cached
            market_kpis.record_request(cached=True, stale=False, source=(cached[0].get("source") if cached else None))
            return cached[:limit]

    try:
        raw_bars = fetch_history(symbol, interval=interval)
    except RuntimeError as exc:
        # provider unavailable (optional dependency)
        market_kpis.record_provider_error()
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Unexpected error while fetching history")
        market_kpis.record_provider_error()
        raise HTTPException(status_code=502, detail="Failed to fetch market data") from exc

    normalized = _normalize_bars(raw_bars)
    if not normalized:
        raise HTTPException(status_code=404, detail="No price bars available for symbol")

    if len(normalized) < min(limit, MIN_BARS):
        raise HTTPException(status_code=422, detail=f"Not enough bars returned (got {len(normalized)}; need at least {min(limit, MIN_BARS)})")

    trimmed = normalized[-limit:]
    cache_service.set_json(cache_key, trimmed, ttl=CACHE_TTL_SECONDS)
    # record successful provider request (not cached)
    market_kpis.record_request(cached=False, stale=False, source=(trimmed[0].get("source") if trimmed else None))
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
