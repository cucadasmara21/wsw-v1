from __future__ import annotations

import hashlib
import logging
import math
import struct

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Query
from fastapi import Response
from fastapi import status
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from database import get_db, engine
from sqlalchemy.exc import ProgrammingError
from services.universe_sources import legacy_assets_relation

logger = logging.getLogger(__name__)
router = APIRouter()

_POINTS_STRUCT = struct.Struct("<HHII")


def _ensure_assets_view_best_effort() -> None:
    """
    Best-effort Postgres bridge:
      public.assets -> public.universe_assets

    IMPORTANT: runs in its own transaction scope to avoid poisoning pooled connections.
    """
    if settings.USE_SQLITE:
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE OR REPLACE VIEW public.assets AS SELECT * FROM public.universe_assets;"))
    except Exception as e:
        logger.debug("could not ensure public.assets view: %s: %s", type(e).__name__, e)

def _stable_int_id(v) -> int:
    """
    Legacy endpoints historically assumed integer IDs.
    In Postgres/V8 mode, ids may be UUIDs; we map them deterministically to a uint32-range int.
    """
    try:
        return int(v)
    except Exception:
        s = str(v)
        h = hashlib.sha256(s.encode("utf-8")).digest()
        return int.from_bytes(h[:4], "big") & 0x7FFFFFFF


def _clamp_u16(n: int) -> int:
    # Clamp ONLY for legacy uint16 packing.
    if n < 0:
        return 0
    if n > 65535:
        return 65535
    return int(n)


def hash_symbol_to_coords(symbol: str) -> tuple[int, int]:
    """
    Generate deterministic uint16 x,y coordinates from symbol using SHA256.
    Works with AST000123 style symbols and regular tickers.
    Returns (x_u16, y_u16) in [0..65535].
    """
    # Use SHA256 for stable, well-distributed hash
    h = hashlib.sha256(symbol.encode('utf-8')).digest()
    
    # Extract two uint16 values from hash bytes
    # Use first 4 bytes for x, next 4 bytes for y
    x_bytes = h[0:4]
    y_bytes = h[4:8]
    
    # Convert to uint32 then take modulo 65536 for uint16 range
    x_u32 = int.from_bytes(x_bytes, byteorder='big') & 0xFFFFFFFF
    y_u32 = int.from_bytes(y_bytes, byteorder='big') & 0xFFFFFFFF
    
    x_u16 = (x_u32 % 65536) & 0xFFFF
    y_u16 = (y_u32 % 65536) & 0xFFFF
    
    return x_u16, y_u16


def compute_galaxy_position(asset_id: int, symbol: str, tax32: int) -> tuple[int, int]:
    """
    Compute galaxy position from symbol hash.
    Uses polar coordinates with power-law distribution for clustering.
    """
    # Generate base coordinates from symbol hash
    x_base, y_base = hash_symbol_to_coords(symbol)
    
    # Convert to normalized [0,1] range
    px = x_base / 65535.0
    py = y_base / 65535.0
    
    # Optional: Apply power-law distribution for clustering (if needed)
    # For now, use uniform distribution for maximum spread
    # Can be adjusted later for clustering by macro/group
    
    # Ensure in valid range and convert back to uint16
    px = max(0.0, min(1.0, px))
    py = max(0.0, min(1.0, py))
    
    x_u16 = int(px * 65535.0) & 0xFFFF
    y_u16 = int(py * 65535.0) & 0xFFFF
    
    return x_u16, y_u16


@router.get("/points.meta")
def points_meta(
    db: Session = Depends(get_db),
    limit: int = Query(100000, ge=0, le=1_000_000),
) -> dict:
    try:
        rel = legacy_assets_relation()
        if settings.USE_SQLITE:
            row = db.execute(text("SELECT COUNT(1) AS c FROM assets")).fetchone()
        else:
            row = db.execute(text(f"SELECT COUNT(1) AS c FROM {rel}")).fetchone()
        count = int(row.c) if row and row.c is not None else 0
        if count > int(limit):
            count = int(limit)
        bytes_count = count * 12
    except Exception as e:
        logger.warning(f"points.meta failed: {e}")
        count = 0
        bytes_count = 0
    return {"count": count, "bytes": bytes_count, "stride": 12}


@router.get("/tree")
def universe_tree(db: Session = Depends(get_db)) -> dict:
    try:
        return {"groups": []}
    except Exception as e:
        logger.warning(f"universe/tree failed: {e}")
        return {"groups": []}


@router.get("/debug_coords")
def debug_coords(
    db: Session = Depends(get_db),
    limit: int = Query(100000, ge=0, le=1_000_000),
) -> dict:
    """
    Debug endpoint to validate coordinate generation.
    Returns min/max and unique counts for x/y coordinates.
    """
    try:
        if settings.USE_SQLITE:
            rows = db.execute(
                text(
                    """
                    SELECT
                      id,
                      symbol,
                      COALESCE(x, 0.0) AS x,
                      COALESCE(y, 0.0) AS y,
                      COALESCE(titan_taxonomy32, 0) AS titan_taxonomy32
                    FROM assets
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).fetchall()
        else:
            rel = legacy_assets_relation()
            rows = db.execute(
                text(
                    f"""
                    SELECT
                      asset_id AS id,
                      symbol,
                      COALESCE(x, 0.0) AS x,
                      COALESCE(y, 0.0) AS y,
                      COALESCE(taxonomy32, 0) AS titan_taxonomy32
                    FROM {rel}
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).fetchall()
    except Exception as e:
        logger.error(f"debug_coords query failed: {e}")
        return {
            "error": str(e),
            "count": 0,
            "min_x": 0,
            "max_x": 0,
            "min_y": 0,
            "max_y": 0,
            "unique_x": 0,
            "unique_y": 0,
            "degenerate": True
        }

    n = len(rows)
    if n == 0:
        return {
            "count": 0,
            "min_x": 0,
            "max_x": 0,
            "min_y": 0,
            "max_y": 0,
            "unique_x": 0,
            "unique_y": 0,
            "degenerate": True
        }

    min_x = 65535
    max_x = 0
    min_y = 65535
    max_y = 0
    unique_x_set = set()
    unique_y_set = set()

    for r in rows:
        asset_id = _stable_int_id(r.id)
        symbol = str(r.symbol) if r.symbol else f"ASSET-{asset_id}"
        tax32 = int(r.titan_taxonomy32) & 0xFFFFFFFF
        
        xf = float(r.x) if r.x is not None else None
        yf = float(r.y) if r.y is not None else None
        
        use_fallback = False
        if xf is None or yf is None:
            use_fallback = True
        elif xf == 0.0 and yf == 0.0:
            use_fallback = True
        elif xf < 0.0 or xf > 1.0 or yf < 0.0 or yf > 1.0:
            use_fallback = True
        elif math.isnan(xf) or math.isnan(yf):
            use_fallback = True

        if use_fallback:
            x_u16, y_u16 = compute_galaxy_position(asset_id, symbol, tax32)
        else:
            xf = max(0.0, min(1.0, xf))
            yf = max(0.0, min(1.0, yf))
            x_u16 = _clamp_u16(int(xf * 65535.0))
            y_u16 = _clamp_u16(int(yf * 65535.0))

        if x_u16 < min_x:
            min_x = x_u16
        if x_u16 > max_x:
            max_x = x_u16
        if y_u16 < min_y:
            min_y = y_u16
        if y_u16 > max_y:
            max_y = y_u16

        unique_x_set.add(x_u16)
        unique_y_set.add(y_u16)

    unique_x_count = len(unique_x_set)
    unique_y_count = len(unique_y_set)
    degenerate = (min_x == max_x) or (min_y == max_y)

    return {
        "count": n,
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "unique_x": unique_x_count,
        "unique_y": unique_y_count,
        "degenerate": degenerate,
        "x_range": max_x - min_x if not degenerate else 0,
        "y_range": max_y - min_y if not degenerate else 0
    }


@router.get("/points.symbols")
def points_symbols(
    db: Session = Depends(get_db),
    limit: int = Query(100000, ge=0, le=1_000_000),
) -> dict:
    try:
        if settings.USE_SQLITE:
            rows = db.execute(
                text(
                    """
                    SELECT id, symbol
                    FROM assets
                    ORDER BY id
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).fetchall()
        else:
            rel = legacy_assets_relation()
            rows = db.execute(
                text(
                    f"""
                    SELECT asset_id AS id, symbol
                    FROM {rel}
                    ORDER BY asset_id
                    LIMIT :limit
                    """
                ),
                {"limit": int(limit)},
            ).fetchall()
        symbols = [{"id": _stable_int_id(r.id), "symbol": str(r.symbol) if r.symbol else f"ASSET-{r.id}"} for r in rows]
        return {"symbols": symbols}
    except Exception as e:
        logger.warning(f"points.symbols failed: {e}")
        return {"symbols": []}


@router.get("/points.bin")
def points_bin(
    db: Session = Depends(get_db),
    limit: int = Query(100000, ge=0, le=1_000_000),
) -> Response:
    """
    Serve points.bin binary buffer.
    Uses shared buffer service if initialized, otherwise falls back to DB query.
    """
    limit_val = int(limit)
    
    # Try to use shared buffer service (faster, thread-safe)
    try:
        from services.points_buffer_service import get_points_buffer_service
        buffer_service = get_points_buffer_service()
        
        if buffer_service.is_initialized():
            buf = buffer_service.get_buffer()
            if buf:
                buf_bytes = bytes(buf) if not isinstance(buf, bytes) else buf
                n_points = len(buf_bytes) // _POINTS_STRUCT.size
                
                if len(buf_bytes) == 0:
                    logger.warning("[points.bin] buffer_service returned empty buffer (bytes=0), falling back to DB")
                elif len(buf_bytes) % _POINTS_STRUCT.size != 0:
                    logger.warning(f"[points.bin] buffer_service buffer size not multiple of stride: bytes={len(buf_bytes)}, stride={_POINTS_STRUCT.size}, falling back to DB")
                else:
                    logger.info(
                        "[points.bin] buffer_service: limit=%s source=buffer_service n_points=%s bytes=%s stride_ok=True head=%s",
                        limit_val,
                        n_points,
                        len(buf_bytes),
                        buf_bytes[:16].hex() if len(buf_bytes) >= 16 else "SHORT"
                    )
                    return Response(
                        content=buf_bytes,
                        media_type="application/octet-stream",
                    headers={
                        "Cache-Control": "no-store",
                        "X-WSW-Points-Count": str(n_points),
                        "X-WSW-Reason": "buffer_service",
                    }
                    )
            else:
                logger.warning("[points.bin] buffer_service returned None, falling back to DB")
    except Exception as e:
        logger.debug(f"Buffer service not available, falling back to DB: {e}")
    
    # Fallback: query database (original behavior)
    try:
        logger.info(f"[points.bin] querying DB: limit={limit_val}")
        if settings.USE_SQLITE:
            rows = db.execute(
                text(
                    """
                    SELECT
                      id,
                      symbol,
                      COALESCE(x, 0.0) AS x,
                      COALESCE(y, 0.0) AS y,
                      COALESCE(meta32, 0) AS meta32,
                      COALESCE(titan_taxonomy32, 0) AS titan_taxonomy32
                    FROM assets
                    ORDER BY id
                    LIMIT :limit
                    """
                ),
                {"limit": limit_val},
            ).fetchall()
        else:
            # Postgres canonical: query universe_assets directly (never depend on public.assets view).
            rel = "public.universe_assets"
            rows = db.execute(
                text(
                    f"""
                    SELECT
                      asset_id AS id,
                      symbol,
                      COALESCE(x, 0.0) AS x,
                      COALESCE(y, 0.0) AS y,
                      COALESCE(meta32, 0) AS meta32,
                      COALESCE(taxonomy32, 0) AS titan_taxonomy32
                    FROM {rel}
                    ORDER BY asset_id
                    LIMIT :limit
                    """
                ),
                {"limit": limit_val},
            ).fetchall()
        n_rows = len(rows)
        logger.info(f"[points.bin] DB query returned n_rows={n_rows}")
    except Exception as e:
        # Transaction hygiene: rollback to avoid leaving the session in failed state.
        try:
            db.rollback()
        except Exception:
            pass

        # Deterministic fallback: return a synthetic point cloud so the canvas draws TODAY.
        logger.exception(f"[points.bin] query failed: limit={limit_val}. Using synthetic fallback. error={e}")
        rows = []

    n = len(rows)
    if n == 0:
        # Deterministic synthetic fallback (200..2000 points, bounded by limit).
        n = max(200, min(limit_val, 2000))
        logger.warning(f"[points.bin] no rows available; returning synthetic fallback n={n} (limit={limit_val})")
        buf = bytearray(n * _POINTS_STRUCT.size)
        mv = memoryview(buf)
        off = 0
        for i in range(n):
            sym = f"SYN{i:06d}"
            x_u16, y_u16 = hash_symbol_to_coords(sym)
            tax32 = (i % 2048) & 0xFFFFFFFF
            meta32 = ((i % 255) | ((i % 255) << 8) | ((i % 3) << 16)) & 0xFFFFFFFF
            _POINTS_STRUCT.pack_into(mv, off, _clamp_u16(x_u16), _clamp_u16(y_u16), tax32, meta32)
            off += _POINTS_STRUCT.size

        buf_bytes = bytes(buf)
        logger.info(
            "[points.bin] synthetic: limit=%s n_points=%s bytes=%s stride_ok=True head=%s",
            limit_val,
            n,
            len(buf_bytes),
            buf_bytes[:16].hex() if len(buf_bytes) >= 16 else "EMPTY",
        )
        return Response(
            content=buf_bytes,
            media_type="application/octet-stream",
            headers={
                "Cache-Control": "no-store",
                "X-WSW-Points-Count": str(n),
                "X-WSW-Format": "legacy-u16xy-u32tax-meta",
                "X-WSW-Stride": str(_POINTS_STRUCT.size),
                "X-WSW-Reason": "synthetic_empty_db",
            },
        )

    buf = bytearray(n * _POINTS_STRUCT.size)
    mv = memoryview(buf)
    off = 0

    min_x = 65535
    max_x = 0
    min_y = 65535
    max_y = 0
    unique_x_set = set()
    unique_y_set = set()

    for idx, r in enumerate(rows):
        asset_id = _stable_int_id(r.id)
        symbol = str(r.symbol) if r.symbol else f"ASSET-{asset_id}"
        tax32 = int(r.titan_taxonomy32) & 0xFFFFFFFF
        
        xf = float(r.x) if r.x is not None else None
        yf = float(r.y) if r.y is not None else None
        
        use_fallback = False
        if xf is None or yf is None:
            use_fallback = True
        elif xf == 0.0 and yf == 0.0:
            use_fallback = True
        elif xf < 0.0 or xf > 1.0 or yf < 0.0 or yf > 1.0:
            use_fallback = True
        elif math.isnan(xf) or math.isnan(yf):
            use_fallback = True

        if use_fallback:
            x_u16, y_u16 = compute_galaxy_position(asset_id, symbol, tax32)
        else:
            xf = max(0.0, min(1.0, xf))
            yf = max(0.0, min(1.0, yf))
            x_u16 = _clamp_u16(int(xf * 65535.0))
            y_u16 = _clamp_u16(int(yf * 65535.0))

        if idx < 5 and settings.DEBUG:
            logger.debug(f"points.bin[{idx}]: id={asset_id}, symbol={symbol}, xf={xf}, yf={yf}, x_u16={x_u16}, y_u16={y_u16}")

        if x_u16 < min_x:
            min_x = x_u16
        if x_u16 > max_x:
            max_x = x_u16
        if y_u16 < min_y:
            min_y = y_u16
        if y_u16 > max_y:
            max_y = y_u16

        # Track unique coordinates for all points
        unique_x_set.add(x_u16)
        unique_y_set.add(y_u16)

        meta32 = int(r.meta32) & 0xFFFFFFFF

        _POINTS_STRUCT.pack_into(mv, off, _clamp_u16(x_u16), _clamp_u16(y_u16), tax32, meta32)
        off += _POINTS_STRUCT.size

    unique_x_count = len(unique_x_set)
    unique_y_count = len(unique_y_set)
    
    buf_bytes = bytes(buf)
    
    # Log before returning
    logger.info(
        "[points.bin] limit=%s count=%s bytes=%s head=%s",
        limit_val,
        n,
        len(buf_bytes),
        buf_bytes[:16].hex() if len(buf_bytes) >= 16 else "EMPTY"
    )
    
    if settings.DEBUG:
        logger.info(f"points.bin: n={n}, x_range=[{min_x}..{max_x}], y_range=[{min_y}..{max_y}], unique_x={unique_x_count}, unique_y={unique_y_count}")
        
        if min_x == max_x or min_y == max_y:
            logger.error(f"DEGENERATE_XY: x_range=[{min_x}..{max_x}], y_range=[{min_y}..{max_y}]")
        elif unique_x_count < 100 or unique_y_count < 100:
            logger.warning(f"LOW_DIVERSITY: unique_x={unique_x_count}, unique_y={unique_y_count}")

    return Response(
        content=buf_bytes,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-WSW-Points-Count": str(n),
            "X-WSW-Format": "legacy-u16xy-u32tax-meta",
            "X-WSW-Stride": str(_POINTS_STRUCT.size),
            "X-WSW-Reason": "ok",
        }
    )


@router.get("/diag")
def universe_diag(db: Session = Depends(get_db)) -> dict:
    """
    Dev-oriented diagnostics to explain empty points/snapshots.
    Returns counts and active DB scheme. Disabled unless DEBUG=true.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=404, detail="Not found")
    rel = legacy_assets_relation()
    try:
        assets_count = int(db.execute(text(f"SELECT COUNT(*) FROM {rel}")).scalar() or 0)
    except Exception as e:
        assets_count = 0
        logger.warning(f"universe/diag count failed: {e}")
    return {
        "assets_relation": rel,
        "assets_count": assets_count,
        "db_scheme": "sqlite" if settings.USE_SQLITE else "postgresql",
    }
