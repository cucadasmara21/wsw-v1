from __future__ import annotations

"""
Route A (TITAN V8) assets endpoints (PostgreSQL-only).

Contract:
- `/api/assets?limit=50` returns JSON 200 list sourced from `public.assets` (TABLE).
- No ORM usage here (prevents SQLAlchemy mapper/DDL issues from impacting operability).

Validation (DoD snippets):
- curl.exe -i "http://127.0.0.1:8000/api/assets?limit=50"
- psql: SELECT COUNT(*) FROM public.assets;
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from database import engine

router = APIRouter(tags=["assets"])


@router.get("", include_in_schema=False)
@router.get("/", summary="List Route A assets (Postgres canonical)")
async def get_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    q: Optional[str] = Query(None, description="Search by symbol or name (case-insensitive)"),
):
    """
    Route A: list assets from `public.assets` (TABLE).

    Response shape is intentionally stable for the UI:
    - id (int): row_number() over (symbol) for display only
    - symbol, name, sector
    - taxonomy32/meta32 (BIGINT in SQL; clients may mask to uint32 when packing)
    """
    qp = None
    if q:
        qp = f"%{q}%"

    sql = text(
        """
        SELECT
          row_number() OVER (ORDER BY symbol) AS id,
          symbol,
          name,
          sector,
          taxonomy32::bigint AS taxonomy32,
          meta32::bigint AS meta32
        FROM public.assets
        WHERE (:qp IS NULL OR symbol ILIKE :qp OR name ILIKE :qp)
        ORDER BY symbol
        OFFSET :skip
        LIMIT :limit;
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(sql, {"skip": int(skip), "limit": int(limit), "qp": qp}).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Route A /api/assets failed: {type(e).__name__}: {e}")


@router.get("/{asset_id}", summary="Get asset by id")
async def get_asset(asset_id: int):
    """Return asset by id or 404 if not found."""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id, symbol, name, sector FROM public.assets WHERE id = :aid"),
                {"aid": asset_id},
            ).mappings().first()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Route A /api/assets/{{id}} failed: {type(e).__name__}: {e}")
    if not row:
        raise HTTPException(status_code=404, detail="Asset not found")
    return dict(row)


@router.get("/detail", summary="Get asset detail with price data")
async def get_asset_detail(
    symbol: str = Query(..., description="Asset symbol"),
):
    """
    Get asset detail with price and sparkline data.
    Returns mock data if price data not available.
    """
    # Route A: validate symbol exists via canonical view (Postgres).
    try:
        with engine.connect() as conn:
            ok = bool(
                conn.execute(
                    text("SELECT EXISTS(SELECT 1 FROM public.assets WHERE symbol = :s)"),
                    {"s": symbol},
                ).scalar()
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Route A /api/assets/detail failed: {type(e).__name__}: {e}")

    if not ok:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    import random
    import time
    
    base_price = 100.0 + (hash(symbol) % 200)
    change_pct = (hash(symbol + "change") % 100) / 10.0 - 5.0
    
    sparkline = []
    for i in range(20):
        seed = hash(f"{symbol}_{i}")
        random.seed(seed)
        sparkline.append(base_price + random.uniform(-10, 10))
    
    return {
        "symbol": symbol,
        "name": f"Asset {symbol}",
        "lastPrice": base_price,
        "changePercent": change_pct,
        "sparkline": sparkline
    }

