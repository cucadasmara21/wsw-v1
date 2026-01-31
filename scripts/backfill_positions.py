from __future__ import annotations

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from database import SessionLocal
from database import engine
from scripts.ensure_titan_schema import ensure_schema

logger = logging.getLogger(__name__)


def splitmix32(x: int) -> int:
    x = (x + 0x9E3779B9) & 0xFFFFFFFF
    x ^= (x >> 16)
    x = (x * 0x85EBCA6B) & 0xFFFFFFFF
    x ^= (x >> 13)
    x = (x * 0xC2B2AE35) & 0xFFFFFFFF
    x ^= (x >> 16)
    return x


def compute_fallback_position(asset_id: int, tax32: int) -> tuple[float, float]:
    h1 = splitmix32(asset_id ^ tax32 ^ 0xA5A5A5A5)
    h2 = splitmix32(asset_id ^ (tax32 << 1) ^ 0x5A5A5A5A)
    x_u16 = h1 & 0xFFFF
    y_u16 = h2 & 0xFFFF
    x = float(x_u16) / 65535.0
    y = float(y_u16) / 65535.0
    return x, y


def main() -> None:
    ensure_schema(engine)
    
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id, x, y, COALESCE(titan_taxonomy32, 0) AS titan_taxonomy32, COALESCE(meta32, 0) AS meta32
                FROM assets
                WHERE x IS NULL OR y IS NULL
                """
            )
        ).fetchall()
        
        updates = []
        for r in rows:
            asset_id = int(r.id)
            tax32 = int(r.titan_taxonomy32) & 0xFFFFFFFF
            meta32 = int(r.meta32) & 0xFFFFFFFF
            
            x, y = compute_fallback_position(asset_id, tax32)
            
            updates.append({
                "id": asset_id,
                "x": x,
                "y": y,
                "titan_taxonomy32": tax32,
                "meta32": meta32
            })
        
        if updates:
            db.execute(
                text(
                    """
                    UPDATE assets
                    SET x = :x, y = :y, titan_taxonomy32 = :titan_taxonomy32, meta32 = :meta32
                    WHERE id = :id
                    """
                ),
                updates
            )
            db.commit()
            logger.info(f"Backfilled {len(updates)} assets with deterministic positions")
        else:
            logger.info("No assets need position backfill")
    except Exception as e:
        logger.error(f"Backfill failed: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
