#!/usr/bin/env python3
"""
Bootstrap legacy source universe (synthetic) into Postgres.

Creates:
- source_assets(asset_id uuid pk, symbol, sector, market_cap, country, x,y,z, meta32, titan_taxonomy32)
- prices(asset_id uuid, t timestamptz, close float8)

Design:
- Deterministic generation (seeded).
- Distribution: log-normal radius per sector ring, angle uniform, z normal.
- taxonomy32 (zeroless packing): [Sector(4b)|Industry(6b)|Risk(3b)|Volatility(5b)|Reserved(14b)]
- meta32: stable uint32 derived from index (can be extended later).
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import struct
import uuid
from dataclasses import dataclass
from typing import Dict, List, Tuple

import asyncpg
import numpy as np

SECTORS: List[str] = ["TECH", "FIN", "HLTH", "ENR", "INDS", "CONS", "COMM", "MATS"]
COUNTRIES: List[str] = ["US", "ES", "DE", "FR", "UK", "NL", "IT", "CH"]

def dsn_async() -> str:
    dsn = os.getenv("DATABASE_DSN_ASYNC") or os.getenv("DATABASE_URL") or ""
    dsn = dsn.strip()
    # Accept SQLAlchemy URL and normalize for asyncpg
    if dsn.startswith("postgresql+psycopg://"):
        dsn = "postgresql://" + dsn[len("postgresql+psycopg://"):]
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if not dsn.startswith("postgresql://"):
        raise SystemExit("ERROR: DATABASE_URL / DATABASE_DSN_ASYNC must be postgresql://... (asyncpg-compatible)")
    return dsn

def pack_taxonomy32(sector_id: int, industry_id: int, risk: int, vol: int) -> int:
    sector_id &= 0xF       # 4b
    industry_id &= 0x3F    # 6b
    risk &= 0x7            # 3b
    vol &= 0x1F            # 5b
    reserved = 0           # 14b
    return (sector_id << 28) | (industry_id << 22) | (risk << 19) | (vol << 14) | reserved

@dataclass(frozen=True)
class AssetRow:
    asset_id: uuid.UUID
    symbol: str
    sector: str
    market_cap: float
    country: str
    x: float
    y: float
    z: float
    meta32: int
    titan_taxonomy32: int

async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS source_assets (
      asset_id UUID PRIMARY KEY,
      symbol TEXT NOT NULL UNIQUE,
      sector TEXT NOT NULL,
      market_cap DOUBLE PRECISION NOT NULL,
      country TEXT NOT NULL,
      x REAL NOT NULL,
      y REAL NOT NULL,
      z REAL NOT NULL,
      meta32 INTEGER NOT NULL,
      titan_taxonomy32 INTEGER NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_source_assets_sector ON source_assets(sector);")
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS prices (
      asset_id UUID NOT NULL,
      t TIMESTAMPTZ NOT NULL,
      close DOUBLE PRECISION NOT NULL,
      PRIMARY KEY(asset_id, t)
    );
    """)
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_prices_asset ON prices(asset_id);")

async def reset_tables(conn: asyncpg.Connection) -> None:
    await conn.execute("TRUNCATE TABLE prices;")
    await conn.execute("TRUNCATE TABLE source_assets;")

def generate_assets(n: int, seed: int) -> List[AssetRow]:
    rng = np.random.default_rng(seed)
    rows: List[AssetRow] = []

    # sector ring radii to create visible structure (deterministic)
    sector_ring = {s: 1.0 + i * 0.35 for i, s in enumerate(SECTORS)}

    for i in range(n):
        sector = SECTORS[i % len(SECTORS)]
        country = COUNTRIES[(i // len(SECTORS)) % len(COUNTRIES)]

        # Market cap log-normal (synthetic)
        market_cap = float(rng.lognormal(mean=10.0, sigma=1.0))  # ~ e^10 scale
        symbol = f"{sector}{i:05d}"

        # Position (log-normal radius around sector ring)
        ang = float(rng.random() * (2.0 * math.pi))
        r = float(rng.lognormal(mean=0.0, sigma=0.55) * sector_ring[sector])
        x = float(math.cos(ang) * r)
        y = float(math.sin(ang) * r)
        z = float(rng.normal(loc=0.0, scale=0.18))

        sector_id = SECTORS.index(sector) & 0xF
        industry_id = (i // 16) & 0x3F
        risk = int(rng.integers(0, 8))
        vol = int(min(31, max(0, int(abs(rng.normal(10, 6))))))  # 0..31
        taxonomy32 = pack_taxonomy32(sector_id, industry_id, risk, vol)

        meta32 = i & 0xFFFFFFFF

        rows.append(AssetRow(
            asset_id=uuid.uuid4(),
            symbol=symbol,
            sector=sector,
            market_cap=market_cap,
            country=country,
            x=x, y=y, z=z,
            meta32=int(meta32),
            titan_taxonomy32=int(taxonomy32),
        ))
    return rows

def generate_prices(rows: List[AssetRow], days: int, seed: int) -> List[Tuple[uuid.UUID, str, float]]:
    rng = np.random.default_rng(seed + 1337)
    out: List[Tuple[uuid.UUID, str, float]] = []

    # fixed timeline (UTC) as ISO strings (asyncpg can cast)
    # simple random walk per asset
    base_ts = np.datetime64("2024-01-01T00:00:00Z")
    for r in rows:
        price = float(rng.lognormal(mean=3.6, sigma=0.35))  # ~ 36ish
        drift = float(rng.normal(0.0002, 0.0015))
        vol = float(abs(rng.normal(0.01, 0.005)))
        for d in range(days):
            ts = (base_ts + np.timedelta64(d, "D")).astype("datetime64[ms]").astype(str)
            shock = float(rng.normal(drift, vol))
            price = max(0.1, price * (1.0 + shock))
            out.append((r.asset_id, ts, float(price)))
    return out

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    dsn = dsn_async()
    conn = await asyncpg.connect(dsn)
    try:
        await ensure_schema(conn)
        if args.reset:
            await reset_tables(conn)

        existing = await conn.fetchval("SELECT COUNT(*) FROM source_assets;")
        if existing and not args.reset:
            print(f"[INFO] source_assets already has {existing} rows. Use --reset to rebuild.")
            return

        print(f"[INFO] Generating {args.n} synthetic assets...")
        assets = generate_assets(args.n, args.seed)

        print(f"[INFO] Inserting {len(assets)} assets...")
        await conn.executemany(
            """
            INSERT INTO source_assets(asset_id, symbol, sector, market_cap, country, x, y, z, meta32, titan_taxonomy32)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            """,
            [(a.asset_id, a.symbol, a.sector, a.market_cap, a.country, a.x, a.y, a.z, a.meta32, a.titan_taxonomy32) for a in assets]
        )

        prices = generate_prices(assets, args.days, args.seed)
        print(f"[INFO] Inserting {len(prices)} price records...")
        # For 300k rows: COPY is faster
        await conn.copy_records_to_table("prices", records=prices, columns=["asset_id", "t", "close"])

        c_assets = await conn.fetchval("SELECT COUNT(*) FROM source_assets;")
        c_prices = await conn.fetchval("SELECT COUNT(*) FROM prices;")
        print(f"[OK] Bootstrap complete. source_assets={c_assets} prices={c_prices}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
