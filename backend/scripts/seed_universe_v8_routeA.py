#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import asyncpg  # type: ignore

from backend.db.dsn import get_asyncpg_dsn
from services.vertex28 import VERTEX28_STRIDE, pack_vertex28


def _clamp01(v: float) -> float:
    if v <= 0.0:
        return 0.0
    if v >= 1.0:
        return 1.0
    return v


def stable_f01(symbol: str, salt: str) -> float:
    h = hashlib.sha256((salt + ":" + symbol).encode("utf-8")).digest()
    return (int.from_bytes(h[:4], "big") % 1_000_000) / 1_000_000.0


def morton63_from_unit_xyz(x: float, y: float, z: float) -> int:
    def q21(u: float) -> int:
        u = _clamp01(float(u))
        return int(u * ((1 << 21) - 1)) & 0x1FFFFF

    qx, qy, qz = q21(x), q21(y), q21(z)
    out = 0
    for i in range(21):
        out |= ((qx >> i) & 1) << (3 * i)
        out |= ((qy >> i) & 1) << (3 * i + 1)
        out |= ((qz >> i) & 1) << (3 * i + 2)
    return out & 0x7FFFFFFFFFFFFFFF


def _flags_u32(i: int) -> int:
    # Deterministic, non-zero u32.
    return (0xA5A50000 | (i & 0xFFFF)) & 0xFFFFFFFF


def _meta32_u32(i: int) -> int:
    # deterministic meta32 bits (not used by Route A snapshot, retained for schema completeness)
    shock = i % 255
    risk = (i * 7) % 255
    trend = i % 3
    vital = (i * 13) % 63
    macro = (i * 17) % 255
    return (shock & 0xFF) | ((risk & 0xFF) << 8) | ((trend & 0x3) << 16) | ((vital & 0x3F) << 18) | ((macro & 0xFF) << 24)


def iter_rows(n: int) -> Iterable[Tuple]:
    sectors = ["TECH", "FIN", "HLTH", "ENER", "INDS", "COMM", "MATR", "UTIL"]
    for i in range(int(n)):
        source_id = uuid.uuid4()
        sym = f"SYN{i:06d}"
        x = stable_f01(sym, "x")
        y = stable_f01(sym, "y")
        z = stable_f01(sym, "z") * 0.15
        mort = morton63_from_unit_xyz(x, y, z)
        taxonomy32 = _flags_u32(i)
        meta32 = _meta32_u32(i)
        risk = float((i % 255) / 255.0)
        shock = float(((i * 17) % 255) / 255.0)
        vb = pack_vertex28(int(mort) & 0xFFFFFFFF, int(meta32) & 0xFFFFFFFF, x, y, z, risk, shock)
        if len(vb) != VERTEX28_STRIDE:
            raise RuntimeError("vertex28 stride mismatch")
        yield (
            uuid.uuid4(),  # asset_id (internal)
            source_id,     # source_assets.id + universe_assets.source_id
            sym,
            sectors[i % len(sectors)],
            int(mort),
            int(taxonomy32),
            int(meta32),
            float(x),
            float(y),
            float(z),
            float(risk),
            float(shock),
            vb,
        )


async def _bootstrap(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # Drop dependencies that can block ALTER TYPE in legacy DBs.
    from database import drop_public_assets_type_safe_async

    await drop_public_assets_type_safe_async(conn)
    await conn.execute("DROP MATERIALIZED VIEW IF EXISTS public.universe_snapshot_v8 CASCADE;")

    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public.source_assets (
          asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          id uuid,
          symbol text UNIQUE NOT NULL,
          sector text,
          x real,
          y real,
          z real,
          meta32 bigint,
          titan_taxonomy32 bigint
        );

        CREATE TABLE IF NOT EXISTS public.universe_assets (
          asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          source_id uuid,
          symbol text UNIQUE,
          sector text,
          morton_code bigint,
          taxonomy32 bigint,
          meta32 bigint,
          x real,
          y real,
          z real,
          fidelity_score real,
          spin real,
          vertex_buffer bytea,
          governance_status text NOT NULL DEFAULT 'PROVISIONAL',
          last_quantum_update timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    await conn.execute("ALTER TABLE public.source_assets ADD COLUMN IF NOT EXISTS id uuid;")
    await conn.execute("UPDATE public.source_assets SET id = gen_random_uuid() WHERE id IS NULL;")
    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_source_assets_id ON public.source_assets(id);")
    await conn.execute("ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS source_id uuid;")
    # Ensure BIGINT for taxonomy/meta (idempotent).
    await conn.execute("ALTER TABLE public.universe_assets ALTER COLUMN taxonomy32 TYPE bigint USING taxonomy32::bigint;")
    await conn.execute("ALTER TABLE public.universe_assets ALTER COLUMN meta32 TYPE bigint USING meta32::bigint;")

    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_universe_assets_symbol ON public.universe_assets(symbol);")
    await conn.execute("CREATE INDEX IF NOT EXISTS ix_universe_assets_morton ON public.universe_assets(morton_code);")
    await conn.execute("CREATE INDEX IF NOT EXISTS ix_universe_assets_sector ON public.universe_assets(sector);")

    # Route A staging table (required by runbooks)
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public._stg_universe_assets (
          asset_id uuid,
          source_id uuid,
          symbol text,
          sector text,
          morton_code bigint NOT NULL,
          taxonomy32 bigint NOT NULL,
          meta32 bigint NOT NULL,
          x real,
          y real,
          z real,
          risk real,
          shock real,
          vertex_buffer bytea NOT NULL
        );
        """
    )
    # Ensure columns exist even if table pre-existed (Route A)
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS asset_id uuid;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS source_id uuid;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS symbol text;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS sector text;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS morton_code bigint;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS taxonomy32 bigint;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS meta32 bigint;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS x real;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS y real;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS z real;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS risk real;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS shock real;")
    await conn.execute("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS vertex_buffer bytea;")
    # Enforce UNIQUE(symbol) (Route A pipeline uses symbol as canonical upsert key).
    # Validation (DoD snippet): psql -> SELECT to_regclass('public.ux__stg_universe_assets_symbol');
    await conn.execute("DROP INDEX IF EXISTS public.ix__stg_universe_assets_symbol;")
    await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux__stg_universe_assets_symbol ON public._stg_universe_assets(symbol);")

    # Required MV for fast snapshot reads (Route A).
    await conn.execute(
        """
        CREATE MATERIALIZED VIEW IF NOT EXISTS public.universe_snapshot_v8 AS
        SELECT morton_code, vertex_buffer
        FROM public.universe_assets;
        """
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_universe_snapshot_v8_morton ON public.universe_snapshot_v8(morton_code);"
    )


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=5000)
    ap.add_argument("--batch", type=int, default=1000)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    dsn = get_asyncpg_dsn(default=os.getenv("DATABASE_DSN_ASYNC", ""))
    t0 = time.perf_counter()

    conn = await asyncpg.connect(dsn=dsn)
    lock_acquired = False
    try:
        # Route A: single-writer guard (session-level advisory lock).
        await conn.execute("SELECT pg_advisory_lock(hashtext('wsw_seed_universe_v8'));")
        lock_acquired = True

        async with conn.transaction():
            # Route A: transactional DDL/DML under advisory lock.
            await _bootstrap(conn)
            if args.reset:
                await conn.execute("TRUNCATE TABLE public._stg_universe_assets;")
                await conn.execute("TRUNCATE TABLE public.universe_assets;")
            else:
                await conn.execute("TRUNCATE TABLE public._stg_universe_assets;")

            batch: List[Tuple] = []
            for row in iter_rows(int(args.target)):
                batch.append(row)
                if len(batch) >= int(args.batch):
                    await conn.copy_records_to_table(
                        "_stg_universe_assets",
                        schema_name="public",
                        records=[(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12]) for r in batch],
                        columns=[
                            "asset_id",
                            "source_id",
                            "symbol",
                            "sector",
                            "morton_code",
                            "taxonomy32",
                            "meta32",
                            "x",
                            "y",
                            "z",
                            "risk",
                            "shock",
                            "vertex_buffer",
                        ],
                    )
                    batch.clear()
            if batch:
                await conn.copy_records_to_table(
                    "_stg_universe_assets",
                    schema_name="public",
                    records=[(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11], r[12]) for r in batch],
                    columns=[
                        "asset_id",
                        "source_id",
                        "symbol",
                        "sector",
                        "morton_code",
                        "taxonomy32",
                        "meta32",
                        "x",
                        "y",
                        "z",
                        "risk",
                        "shock",
                        "vertex_buffer",
                    ],
                )

            # Upsert source_assets first to satisfy FK-like join semantics.
            await conn.execute(
                """
                INSERT INTO public.source_assets (id, symbol, sector, x, y, z, meta32, titan_taxonomy32)
                SELECT source_id, symbol, sector, x, y, z, meta32, taxonomy32
                FROM public._stg_universe_assets
                ON CONFLICT (symbol) DO UPDATE SET
                  id=EXCLUDED.id,
                  sector=EXCLUDED.sector,
                  x=EXCLUDED.x, y=EXCLUDED.y, z=EXCLUDED.z,
                  meta32=EXCLUDED.meta32,
                  titan_taxonomy32=EXCLUDED.titan_taxonomy32;
                """
            )

            await conn.execute(
                """
                INSERT INTO public.universe_assets (
                  asset_id, source_id, symbol, sector, morton_code, taxonomy32, meta32, x, y, z, fidelity_score, spin, vertex_buffer
                )
                SELECT
                  asset_id, source_id, symbol, sector, morton_code, taxonomy32, meta32, x, y, z, risk, shock, vertex_buffer
                FROM public._stg_universe_assets
                ON CONFLICT (symbol) DO UPDATE SET
                  source_id=EXCLUDED.source_id,
                  sector=EXCLUDED.sector,
                  morton_code=EXCLUDED.morton_code,
                  taxonomy32=EXCLUDED.taxonomy32,
                  meta32=EXCLUDED.meta32,
                  x=EXCLUDED.x, y=EXCLUDED.y, z=EXCLUDED.z,
                  fidelity_score=EXCLUDED.fidelity_score,
                  spin=EXCLUDED.spin,
                  vertex_buffer=EXCLUDED.vertex_buffer,
                  last_quantum_update=NOW();
                """
            )

            # Ensure join keys are populated.
            await conn.execute("UPDATE public.universe_assets ua SET source_id = sa.id FROM public.source_assets sa WHERE ua.symbol = sa.symbol AND ua.source_id IS NULL;")

            # Refresh MV for snapshot reads (Route A).
            await conn.execute("REFRESH MATERIALIZED VIEW public.universe_snapshot_v8;")

        n = int(await conn.fetchval("SELECT COUNT(*) FROM public.universe_assets;") or 0)
        if args.verify:
            bad = int(await conn.fetchval("SELECT COUNT(*) FROM public.universe_assets WHERE symbol IS NULL OR symbol = '';") or 0)
            if bad != 0:
                raise SystemExit("verify failed: empty symbol rows present")
            vb_bad = int(await conn.fetchval("SELECT COUNT(*) FROM public.universe_assets WHERE octet_length(vertex_buffer) != 28;") or 0)
            if vb_bad != 0:
                raise SystemExit("verify failed: vertex_buffer stride != 28")

        dt = time.perf_counter() - t0
        print(f"OK routeA seed: universe_assets={n} dt={dt:.3f}s")
    finally:
        if lock_acquired:
            try:
                await conn.execute("SELECT pg_advisory_unlock(hashtext('wsw_seed_universe_v8'));")
            except Exception:
                # If unlock fails, closing the connection will release the lock.
                pass
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

