from __future__ import annotations

import math
import time
from typing import List
from typing import Tuple

from sqlalchemy import text

from database import SessionLocal
from database import engine
from scripts.ensure_titan_schema import ensure_schema


def _u32(x: int) -> int:
    return x & 0xFFFFFFFF


def hash32(i: int) -> int:
    x = _u32(i * 2654435761)
    x ^= (x >> 16)
    x = _u32(x * 2246822519)
    x ^= (x >> 13)
    x = _u32(x * 3266489917)
    x ^= (x >> 16)
    return _u32(x)


def splitmix32(seed: int) -> int:
    z = _u32(seed + 0x9E3779B9)
    z = _u32((z ^ (z >> 16)) * 0x85EBCA6B)
    z = _u32((z ^ (z >> 13)) * 0xC2B2AE35)
    z = _u32(z ^ (z >> 16))
    return z


def u01_from_u32(x: int) -> float:
    return (float(x & 0xFFFFFF) + 1.0) / (float(0x1000000) + 2.0)


def gauss2_from_seed(seed: int) -> Tuple[float, float]:
    a = u01_from_u32(splitmix32(seed))
    b = u01_from_u32(splitmix32(seed ^ 0xA5A5A5A5))
    r = math.sqrt(-2.0 * math.log(a))
    t = 2.0 * math.pi * b
    return r * math.cos(t), r * math.sin(t)


DOMAIN_CENTROIDS: List[Tuple[float, float]] = [
    (0.20, 0.25),
    (0.80, 0.25),
    (0.50, 0.50),
    (0.20, 0.80),
    (0.80, 0.80),
    (0.50, 0.15),
]


def pack_meta32(shock8: int, risk8: int, trend2: int, vital6: int, macro8: int) -> int:
    return _u32((shock8 & 0xFF) |
               ((risk8 & 0xFF) << 8) |
               ((trend2 & 0x03) << 16) |
               ((vital6 & 0x3F) << 18) |
               ((macro8 & 0xFF) << 24))


def seed_galaxy(n: int = 10_000) -> None:
    ensure_schema(engine)

    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM assets WHERE symbol LIKE 'SYNT-%'"))
        db.commit()

        ts = int(time.time())
        rows = []

        macro8 = 128

        for i in range(n):
            h = hash32(i)
            
            risk8 = (h >> 0) & 0xFF
            
            trend2_raw = (h >> 8) & 0x03
            trend2 = trend2_raw if trend2_raw != 3 else 2
            
            macro8 = 128
            
            is_zombie = ((h >> 16) & 0xFF) < 13
            
            if is_zombie:
                vital6 = (h >> 24) & 0x05
            else:
                vital6 = 20 + ((h >> 24) & 0x2B)
            
            shock8 = (h >> 0) & 0xFF

            seed = _u32(i ^ (ts * 2654435761))

            domain_idx = splitmix32(seed) % 6
            domain_id = domain_idx + 1
            cluster_id = splitmix32(seed ^ 0x12345678) % 100
            category_id = splitmix32(seed ^ 0x87654321) % 50
            sub_id = splitmix32(seed ^ 0xABCDEF00) % 10
            taxonomy32 = (domain_id << 24) | (cluster_id << 16) | (category_id << 8) | sub_id

            cx, cy = DOMAIN_CENTROIDS[domain_idx]

            r_u = u01_from_u32(splitmix32(seed ^ 0x13579BDF))
            risk = min(1.0, max(0.0, r_u ** 0.55))

            sigma = 0.10 - (0.09 * risk)

            gx, gy = gauss2_from_seed(seed ^ 0xDEADBEEF)
            x = cx + gx * sigma
            y = cy + gy * sigma

            if x < 0.0:
                x = 0.0
            if x > 1.0:
                x = 1.0
            if y < 0.0:
                y = 0.0
            if y > 1.0:
                y = 1.0

            meta32 = pack_meta32(shock8=shock8, risk8=risk8, trend2=trend2, vital6=vital6, macro8=macro8)

            rows.append(
                {
                    "symbol": f"SYNT-{i:06d}",
                    "name": f"Synthetic Asset {i}",
                    "x": float(x),
                    "y": float(y),
                    "titan_taxonomy32": int(taxonomy32),
                    "meta32": int(meta32),
                }
            )

        db.execute(
            text(
                "INSERT INTO assets (symbol, name, x, y, titan_taxonomy32, meta32) "
                "VALUES (:symbol, :name, :x, :y, :titan_taxonomy32, :meta32)"
            ),
            rows,
        )
        db.commit()

    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Seed Titan Galaxy")
    parser.add_argument("--n", type=int, default=10_000, help="Number of assets")
    args = parser.parse_args()
    seed_galaxy(args.n)
    print(f"OK: seeded {args.n} deterministic Titan points")
