from __future__ import annotations

"""Market data endpoints: bars and indicator snapshots."""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from database import get_db
from schemas import MarketBarsResponse, MarketSnapshotResponse
from services import market_data_service, indicators_service
from services.rate_limiter import rate_limiter
from services.market_data_service import market_kpis

router = APIRouter(tags=["market"])
logger = logging.getLogger(__name__)


def _dependency_error_response(code: str, message: str) -> dict:
    """Return standardized dependency error response."""
    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


@router.get("/bars", response_model=MarketBarsResponse, summary="Get OHLCV bars")
def get_market_bars(
    symbol: str = Query(..., min_length=1, description="Ticker symbol, e.g., TSLA"),
    interval: str = Query("1d", description="yfinance interval, e.g., 1d, 1h, 5m"),
    limit: int = Query(200, ge=5, le=1000, description="Number of bars to return"),
    store: bool = Query(False, description="Persist bars to the database"),
    db: Session = Depends(get_db),
):
    """Return normalized OHLCV bars using yfinance (cached) without pandas dependency."""
    try:
        bars = market_data_service.get_bars(symbol, interval=interval, limit=limit, use_cache=True)
    except HTTPException as exc:
        if exc.status_code == 503:
            # yfinance not available - return clear error
            raise HTTPException(
                status_code=503,
                detail=_dependency_error_response(
                    "dependency_missing",
                    "Optional dependency yfinance not installed. Install requirements-optional.txt"
                )
            )
        raise

    if store:
        try:
            market_data_service.persist_price_bars(db, symbol, bars)
        except Exception:
            # best-effort persistence; keep response even if persistence fails
            logger.debug(f"Failed to persist bars for {symbol}", exc_info=True)

    return MarketBarsResponse(
        symbol=symbol,
        interval=interval,
        limit=limit,
        count=len(bars),
        bars=bars,
    )


@router.get("/snapshot", response_model=MarketSnapshotResponse, summary="Compute indicators and risk snapshot")
def get_market_snapshot(
    request: Request,
    symbol: str = Query(..., min_length=1, description="Ticker symbol, e.g., TSLA"),
    interval: str = Query("1d", description="yfinance interval, e.g., 1d, 1h, 5m"),
    limit: int = Query(200, ge=indicators_service.MIN_BARS_FOR_INDICATORS, le=1000, description="Bars used for indicators"),
    persist: bool = Query(True, description="Persist bars and snapshot"),
    db: Session = Depends(get_db),
):
    """Compute and return market snapshot with indicators and risk score."""
    # Simple per-IP rate limiting
    try:
        client_ip = request.client.host if request and request.client else "unknown"
        if not rate_limiter.is_allowed(client_ip):
            market_kpis.record_rate_limited()
            raise HTTPException(status_code=429, detail="Too Many Requests")
    except HTTPException:
        raise
    except Exception:
        # If request or limiter fails unexpectedly, proceed without blocking
        pass
    try:
        bars = market_data_service.get_bars(symbol, interval=interval, limit=limit, use_cache=True)
    except HTTPException as exc:
        if exc.status_code == 503:
            raise HTTPException(
                status_code=503,
                detail=_dependency_error_response(
                    "dependency_missing",
                    "Optional dependency yfinance not installed. Install requirements-optional.txt"
                )
            )
        raise

    snapshot = indicators_service.compute_snapshot(symbol, bars, timeframe=interval)

    # Attach optional fields: cached/stale/source/confidence
    try:
        k = market_kpis.get_stats()
        last = (k.get("last") or {})
        cached = bool(last.get("cached", False))
        stale = bool(last.get("stale", False))
        source = last.get("source") or (bars[0].get("source") if bars else None)

        # Compute confidence based on recency of last bar
        from datetime import datetime
        last_ts_str = bars[-1].get("ts") if bars else None
        conf = 0.0
        if last_ts_str:
            try:
                last_ts = datetime.fromisoformat(str(last_ts_str))
                age_days = max(0.0, (datetime.utcnow() - last_ts).total_seconds() / 86400.0)
                conf = max(0.0, min(1.0, 1.0 - (age_days / 14.0)))
            except Exception:
                conf = 0.0
        market_kpis.add_confidence(conf)

        snapshot.update({
            "cached": cached,
            "stale": stale,
            "source": source,
            "confidence": conf,
        })
    except Exception:
        # Do not fail snapshot if optional enrich fails
        pass

    if persist:
        try:
            market_data_service.persist_price_bars(db, symbol, bars)
        except Exception:
            # persistence is best-effort
            logger.debug(f"Failed to persist bars for {symbol}", exc_info=True)
        try:
            indicators_service.persist_snapshot(db, snapshot)
        except HTTPException:
            raise
        except Exception:
            # do not fail the endpoint if persistence fails
            logger.debug(f"Failed to persist snapshot for {symbol}", exc_info=True)

    return snapshot
