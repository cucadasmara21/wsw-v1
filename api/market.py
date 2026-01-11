from __future__ import annotations

"""Market data endpoints: bars and indicator snapshots."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas import MarketBarsResponse, MarketSnapshotResponse
from services import market_data_service, indicators_service

router = APIRouter(tags=["market"])


@router.get("/bars", response_model=MarketBarsResponse, summary="Get OHLCV bars")
def get_market_bars(
    symbol: str = Query(..., min_length=1, description="Ticker symbol, e.g., TSLA"),
    interval: str = Query("1d", description="yfinance interval, e.g., 1d, 1h, 5m"),
    limit: int = Query(200, ge=5, le=1000, description="Number of bars to return"),
    store: bool = Query(False, description="Persist bars to the database"),
    db: Session = Depends(get_db),
):
    """Return normalized OHLCV bars using yfinance (cached) without pandas dependency."""
    bars = market_data_service.get_bars(symbol, interval=interval, limit=limit, use_cache=True)
    if store:
        try:
            market_data_service.persist_price_bars(db, symbol, bars)
        except Exception:
            # best-effort persistence; keep response even if persistence fails
            pass

    return MarketBarsResponse(
        symbol=symbol,
        interval=interval,
        limit=limit,
        count=len(bars),
        bars=bars,
    )


@router.get("/snapshot", response_model=MarketSnapshotResponse, summary="Compute indicators and risk snapshot")
def get_market_snapshot(
    symbol: str = Query(..., min_length=1, description="Ticker symbol, e.g., TSLA"),
    interval: str = Query("1d", description="yfinance interval, e.g., 1d, 1h, 5m"),
    limit: int = Query(200, ge=indicators_service.MIN_BARS_FOR_INDICATORS, le=1000, description="Bars used for indicators"),
    persist: bool = Query(True, description="Persist bars and snapshot"),
    db: Session = Depends(get_db),
):
    bars = market_data_service.get_bars(symbol, interval=interval, limit=limit, use_cache=True)
    snapshot = indicators_service.compute_snapshot(symbol, bars, timeframe=interval)

    if persist:
        try:
            market_data_service.persist_price_bars(db, symbol, bars)
        except Exception:
            # persistence is best-effort
            pass
        try:
            indicators_service.persist_snapshot(db, snapshot)
        except HTTPException:
            raise
        except Exception:
            # do not fail the endpoint if persistence fails
            pass

    return snapshot
