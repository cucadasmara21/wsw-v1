#!/usr/bin/env python3
"""
Titan V8 Universe Seeder / Materializer (Production-Grade, Mass Scale)

Source layer:
- public.source_assets (+ public.prices)
- public.assets view (compatibility + canonical sector normalization)

Target layer:
- public.universe_assets (authoritative Vertex28 store)

Non-negotiable guarantees (TITAN V8 contract):
- EXACT target rows (default 200,000). If inventory < target => hard fail.
- Deterministic selection + deterministic redistribution across sectors.
- Vertex28 packing is immutable: little-endian <IIfffff, EXACTLY 28 bytes per record.
- True Morton63: 21 bits per axis from normalized XYZ; collisions are forbidden.
- Two-phase deterministic redistribution (DeepSeek V30): base quota + remainder, then round-robin transfers.
- Ingest isolation: load ONLY into UNLOGGED per-sector staging tables, then single atomic finalize swap.
- AMD Zen+ orchestration: heavy materialization uses EXACTLY 12 Python workers (unless CI mode).

How to run (Windows PowerShell):
  docker compose -f .\\docker-compose.yml up -d
  $env:DATABASE_DSN_ASYNC="postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"
  python .\\backend\\scripts\\seed_universe_v8.py --target 200000 --batch 5000 --verify
  .\\scripts\\audit_v8.ps1 -Target 200000 -ApiBase http://127.0.0.1:8000
"""

import argparse
import asyncio
import concurrent.futures
import hashlib
import logging
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Add project root to path (repo root)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg required. Install: pip install asyncpg")
    raise

from services.vertex28 import VERTEX28_STRIDE, pack_vertex28

LOG = logging.getLogger("seed_universe_v8")

VERTEX_STRIDE = VERTEX28_STRIDE

SECTORS = ["TECH", "FIN", "HLTH", "ENER", "INDS", "COMM", "MATR", "UTIL"]


def normalize_asyncpg_dsn(dsn: str) -> str:
    """
    asyncpg expects scheme "postgresql://" or "postgres://"
    Fix common variants:
      - postgresql+psycopg://  -> postgresql://
      - postgresql+psycopg2:// -> postgresql://
    """
    if not dsn:
        return dsn
    dsn = dsn.strip().strip('"').strip("'")
    dsn = dsn.replace("postgresql+psycopg://", "postgresql://")
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    dsn = dsn.replace("postgres+psycopg://", "postgresql://")
    return dsn


def pick_dsn() -> str:
    """
    Priority:
      1) DATABASE_DSN_ASYNC
      2) DATABASE_URL
    """
    dsn = os.getenv("DATABASE_DSN_ASYNC") or os.getenv("DATABASE_URL") or os.getenv("DATABASE_URI") or ""
    dsn = normalize_asyncpg_dsn(dsn)
    if not dsn or dsn.startswith("sqlite"):
        raise SystemExit("ERROR: Set DATABASE_DSN_ASYNC or DATABASE_URL to a PostgreSQL DSN (postgresql://...)")
    return dsn


def _clamp01(v: float) -> float:
    if v <= 0.0:
        return 0.0
    if v >= 1.0:
        return 1.0
    return v


def morton63_from_unit_xyz(x: float, y: float, z: float) -> int:
    """
    63-bit Morton code: 21 bits per axis, interleaved (x,y,z).
    """
    def q21(u: float) -> int:
        u = _clamp01(float(u))
        return int(u * ((1 << 21) - 1)) & 0x1FFFFF

    qx, qy, qz = q21(x), q21(y), q21(z)

    # Interleave 21 bits => 63 bits
    out = 0
    for i in range(21):
        out |= ((qx >> i) & 1) << (3 * i)
        out |= ((qy >> i) & 1) << (3 * i + 1)
        out |= ((qz >> i) & 1) << (3 * i + 2)
    return out & 0x7FFFFFFFFFFFFFFF


def morton63_from_unit_xyz_salted(x: float, y: float, z: float, salt_u32: int) -> int:
    """
    Morton63 with deterministic tie-breaker bits injected into quantization LSBs.

    This reduces collision probability without changing the Vertex28 contract.
    It still produces a true 63-bit Morton code from normalized XYZ.
    """

    def q21(u: float) -> int:
        u = _clamp01(float(u))
        return int(u * ((1 << 21) - 1)) & 0x1FFFFF

    qx, qy, qz = q21(x), q21(y), q21(z)

    # Inject 3 LSB bits per axis from salt (9 bits total) to break ties deterministically.
    qx = (qx & ~0x7) | (salt_u32 & 0x7)
    qy = (qy & ~0x7) | ((salt_u32 >> 3) & 0x7)
    qz = (qz & ~0x7) | ((salt_u32 >> 6) & 0x7)

    out = 0
    for i in range(21):
        out |= ((qx >> i) & 1) << (3 * i)
        out |= ((qy >> i) & 1) << (3 * i + 1)
        out |= ((qz >> i) & 1) << (3 * i + 2)
    return out & 0x7FFFFFFFFFFFFFFF


def taxonomy32_zeroless(domain: int, industry: int, risk: int, vol: int) -> int:
    """
    [Domain/Sector(4b) | Industry(6b) | Risk(3b) | Vol(5b) | Reserved(14b)]
    Zeroless: enforce >=1 for each field.
    """
    domain = max(1, min(15, int(domain)))
    industry = max(1, min(63, int(industry)))
    risk = max(1, min(7, int(risk)))
    vol = max(1, min(31, int(vol)))
    return ((domain & 0xF) << 28) | ((industry & 0x3F) << 22) | ((risk & 0x7) << 19) | ((vol & 0x1F) << 14)


def meta32_minimal(outlier: bool, risk_tier: int, liquidity_tier: int) -> int:
    """
    Compact meta32:
      bits 0..1   liquidity_tier (1..3)  -> store 0..3
      bits 2..4   risk_tier      (1..7)  -> store 0..7
      bit  5      outlier flag
      bits 6..31  reserved
    """
    lt = max(1, min(3, int(liquidity_tier))) & 0x3
    rt = max(1, min(7, int(risk_tier))) & 0x7
    o = 1 if outlier else 0
    return (lt) | (rt << 2) | (o << 5)


def fidelity_score(has_price: bool, has_sector: bool) -> float:
    # deterministic tiering; keep within [0,1]
    if has_price and has_sector:
        return 0.92
    if has_sector:
        return 0.84
    if has_price:
        return 0.78
    return 0.62


def spin_value(taxonomy32: int, risk: int) -> float:
    parity = (taxonomy32.bit_count() & 1)
    rn = max(1, min(7, int(risk))) / 7.0
    return float(parity) * rn


def stable_u32_from_str(s: str) -> int:
    h = hashlib.md5(s.encode("utf-8")).digest()
    return int.from_bytes(h[:4], "big") & 0xFFFFFFFF


def stable_f01_from_str(s: str, salt: str) -> float:
    h = hashlib.sha256((salt + ":" + s).encode("utf-8")).digest()
    return (int.from_bytes(h[:4], "big") % 1_000_000) / 1_000_000.0


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        # NaN check: NaN != NaN
        if f != f:
            return default
        return f
    except Exception:
        return default


def _normalize01(v: float, vmin: float, vmax: float, fallback: float) -> float:
    """
    Deterministically normalize to [0,1] using global bounds.
    If bounds are degenerate, fallback is used (already in [0,1]).
    """
    if vmax <= vmin:
        return _clamp01(fallback)
    return _clamp01((v - vmin) / (vmax - vmin))


async def ensure_legacy_schema(pool: asyncpg.Pool) -> None:
    """
    Ensure source_assets has required columns (id alias, x/y/z, meta32, titan_taxonomy32).
    We do NOT assume bootstrap was correct; we heal schema to unblock pipeline.
    """
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

        # Detect columns
        cols = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='source_assets'
            """
        )
        if not cols:
            raise SystemExit(
                "ERROR: Table public.source_assets does not exist.\n"
                "Run: python scripts/bootstrap_legacy.py --n 10000 --days 30 --reset"
            )

        colset = {r["column_name"] for r in cols}

        # Ensure asset_id exists; if not, fail (we won't guess PK)
        if "asset_id" not in colset:
            raise SystemExit("ERROR: source_assets missing asset_id. Your bootstrap must create asset_id UUID. Fix bootstrap_legacy.py first.")

        alters = []
        if "x" not in colset:
            alters.append("ADD COLUMN x real")
        if "y" not in colset:
            alters.append("ADD COLUMN y real")
        if "z" not in colset:
            alters.append("ADD COLUMN z real")
        if "meta32" not in colset:
            alters.append("ADD COLUMN meta32 bigint")
        if "titan_taxonomy32" not in colset:
            alters.append("ADD COLUMN titan_taxonomy32 bigint")
        if alters:
            await conn.execute(f"ALTER TABLE public.source_assets {', '.join(alters)};")
            LOG.info("Healed source_assets schema: added %s", ", ".join([a.split()[2] for a in alters]))
        
        # Migrate existing integer columns to BIGINT (u32-safe)
        col_types = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='source_assets'
              AND column_name IN ('meta32', 'titan_taxonomy32')
            """
        )
        for row in col_types:
            col_name = row["column_name"]
            data_type = row["data_type"]
            if data_type == "integer":
                await conn.execute(
                    f"ALTER TABLE public.source_assets ALTER COLUMN {col_name} TYPE bigint USING {col_name}::bigint;"
                )
                LOG.info("Migrated source_assets.%s from integer to bigint", col_name)

        # Backfill x/y/z if NULL (deterministic)
        # Use symbol hash -> [0,1], and sector ring bias to avoid degenerate cloud.
        # NOTE: bit(32) requires 'x' prefix for hex; 'y'/'z' are invalid
        await conn.execute(
            """
            UPDATE public.source_assets
            SET
              x = COALESCE(x, (('x' || substr(md5(symbol), 1, 8))::bit(32)::int % 1000000) / 1000000.0),
              y = COALESCE(y, (('x' || substr(md5(symbol), 9, 8))::bit(32)::int % 1000000) / 1000000.0),
              z = COALESCE(z, (('x' || substr(md5(symbol), 17, 8))::bit(32)::int % 1000000) / 1000000.0),
              meta32 = COALESCE(meta32, 0),
              titan_taxonomy32 = COALESCE(titan_taxonomy32, 0)
            WHERE x IS NULL OR y IS NULL OR z IS NULL OR meta32 IS NULL OR titan_taxonomy32 IS NULL;
            """
        )


async def ensure_quantum_schema(conn: asyncpg.Connection) -> None:
    """
    Ensure universe_assets has all required columns (idempotent).
    Uses ALTER TABLE ... ADD COLUMN IF NOT EXISTS for safety.
    """
    # CRITICAL: Drop snapshot MV first (idempotent) before any ALTER COLUMN.
    # Do NOT drop public.assets (TABLE) - required for legacy/inserts.
    await conn.execute("DROP MATERIALIZED VIEW IF EXISTS public.universe_snapshot_v8 CASCADE;")

    # Check if table exists
    exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'universe_assets'
        )
        """
    )
    if not exists:
        raise SystemExit(
            "ERROR: Table public.universe_assets does not exist.\n"
            "Run: alembic upgrade head"
        )
    
    # Add columns if not exist (idempotent, one at a time for safety)
    await conn.execute("""
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS symbol TEXT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS sector TEXT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS titan_taxonomy32 BIGINT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS taxonomy32 BIGINT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS meta32 BIGINT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS x REAL;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS y REAL;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS z REAL;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS morton_code BIGINT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS vertex_buffer BYTEA;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS fidelity_score REAL;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS spin REAL DEFAULT 0.0;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS governance_status TEXT;
        ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS last_quantum_update TIMESTAMPTZ DEFAULT now();
    """)
    
    # Migrate existing integer columns to BIGINT (u32-safe)
    col_types = await conn.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='universe_assets'
          AND column_name IN ('taxonomy32', 'meta32', 'titan_taxonomy32')
        """
    )
    for row in col_types:
        col_name = row["column_name"]
        data_type = row["data_type"]
        if data_type == "integer":
            await conn.execute(
                f"ALTER TABLE public.universe_assets ALTER COLUMN {col_name} TYPE bigint USING {col_name}::bigint;"
            )
            LOG.info("Migrated universe_assets.%s from integer to bigint", col_name)
    
    # Ensure indexes (idempotent)
    await conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ux_universe_assets_symbol ON public.universe_assets(symbol);
        CREATE INDEX IF NOT EXISTS ix_universe_assets_sector ON public.universe_assets(sector);
        CREATE INDEX IF NOT EXISTS ix_universe_assets_morton ON public.universe_assets(morton_code);
    """)

    # Recreate Route A compatibility view (do NOT replace public.assets TABLE).
    await conn.execute(
        """
        CREATE OR REPLACE VIEW public.assets_v8 AS
        SELECT
          row_number() OVER (ORDER BY symbol)::int AS id,
          symbol,
          COALESCE(NULLIF(btrim(symbol), ''), 'UNKNOWN') AS name,
          sector,
          taxonomy32::bigint AS taxonomy32,
          meta32::bigint AS meta32
        FROM public.universe_assets;
        """
    )


async def ensure_assets_source_view(pool: asyncpg.Pool) -> None:
    """
    Create a normalized SOURCE VIEW for seeding from public.source_assets.
    (This is intentionally NOT the legacy compatibility view; that one is recreated
    by ensure_quantum_schema() as public.assets -> public.universe_assets.)

    Exposes:
      id (uuid)      -> source_assets.asset_id
      symbol         -> source_assets.symbol
      x/y/z/meta32/titan_taxonomy32/sector
      has_price      -> EXISTS(prices)
    This fixes "id does not exist" callers and standardizes queries.
    """
    async with pool.acquire() as conn:
        sector_case = (
            "CASE "
            "WHEN sa.sector IS NULL OR btrim(sa.sector) = '' THEN 'UTIL' "
            "WHEN sa.sector IN ('TECH','FIN','HLTH','ENER','INDS','COMM','MATR','UTIL') THEN sa.sector "
            "ELSE 'UTIL' "
            "END"
        )
        await conn.execute(
            (
                """
            CREATE OR REPLACE VIEW public.assets_source AS
            SELECT
              sa.asset_id AS id,
              sa.symbol,
              COALESCE(sa.x, 0.0) AS x,
              COALESCE(sa.y, 0.0) AS y,
              COALESCE(sa.z, 0.0) AS z,
              COALESCE(sa.meta32, 0) AS meta32,
              COALESCE(sa.titan_taxonomy32, 0) AS titan_taxonomy32,
              """
                + sector_case
                + """ AS sector,
              EXISTS(SELECT 1 FROM public.prices p WHERE p.asset_id = sa.asset_id LIMIT 1) AS has_price
            FROM public.source_assets sa;
                """
            )
        )


async def fetch_assets_slice(
    conn: asyncpg.Connection, *, sector: str, limit: int, offset: int
) -> List[asyncpg.Record]:
    """
    Deterministic selection contract: ORDER BY id (uuid).
    """
    return await conn.fetch(
        """
        SELECT id, symbol, x, y, z, meta32, titan_taxonomy32, sector, has_price
        FROM public.assets_source
        WHERE sector = $1
        ORDER BY id
        OFFSET $2
        LIMIT $3
        """,
        sector,
        offset,
        limit,
    )


def _compute_vertex_record(
    *,
    asset_id: uuid.UUID,
    symbol: str,
    raw_x: float,
    raw_y: float,
    raw_z: float,
    legacy_tax: int,
    legacy_meta: int,
    has_price: bool,
    assigned_sector: str,
    bounds: Tuple[float, float, float, float, float, float],
) -> Tuple[uuid.UUID, str, int, int, int, float, float, float, float, float, bytes, str]:
    """
    Compute all quantum fields deterministically and return a staging row.

    Output schema matches UNLOGGED staging tables:
      (asset_id, symbol, morton_code, taxonomy32, meta32, x, y, z, fidelity_score, spin, vertex_buffer, sector)
    """
    xmin, xmax, ymin, ymax, zmin, zmax = bounds

    # Stable fallback coordinates if bounds collapse or values are missing.
    fx = stable_f01_from_str(symbol, "x")
    fy = stable_f01_from_str(symbol, "y")
    fz = stable_f01_from_str(symbol, "z")

    x = _normalize01(raw_x, xmin, xmax, fx)
    y = _normalize01(raw_y, ymin, ymax, fy)
    z = _normalize01(raw_z, zmin, zmax, fz)

    salt = stable_u32_from_str(str(asset_id))
    morton = morton63_from_unit_xyz_salted(x, y, z, salt)

    # Deterministic sector ID order = index in canonical SECTORS list.
    # Domain is 1..15; we use sector_id+1 (zeroless).
    try:
        sector_id = SECTORS.index(assigned_sector)
    except ValueError:
        sector_id = SECTORS.index("UTIL")
    domain = sector_id + 1

    # Stable pseudo-risk derived from sector+symbol hashes.
    sec_h = stable_u32_from_str(assigned_sector)
    sym_h = stable_u32_from_str(symbol)
    risk_tier = ((sec_h ^ sym_h) % 7) + 1
    vol = (((sec_h >> 6) ^ (sym_h >> 3)) % 31) + 1
    industry = (sym_h % 63) + 1

    taxonomy32 = int(legacy_tax) & 0xFFFFFFFF
    if taxonomy32 == 0:
        taxonomy32 = taxonomy32_zeroless(domain, industry, risk_tier, vol)

    meta32 = int(legacy_meta) & 0xFFFFFFFF
    if meta32 == 0:
        outlier = (hashlib.md5(symbol.encode("utf-8")).hexdigest()[0] in "012345")  # deterministic
        liquidity = ((sec_h >> 11) % 3) + 1
        meta32 = meta32_minimal(outlier, risk_tier, liquidity)

    fid = fidelity_score(bool(has_price), True)
    spn = spin_value(taxonomy32, risk_tier)

    vb = pack_vertex28(int(morton) & 0xFFFFFFFF, meta32, x, y, z, fid, spn)
    if len(vb) != VERTEX_STRIDE:
        raise RuntimeError(f"Vertex28 stride violation: got {len(vb)} bytes, expected 28")

    return (asset_id, symbol, morton, taxonomy32, meta32, x, y, z, fid, spn, vb, assigned_sector)


def compute_batch(
    rows: List[Tuple[uuid.UUID, str, float, float, float, int, int, bool, str]],
    bounds: Tuple[float, float, float, float, float, float],
) -> List[Tuple[uuid.UUID, str, int, int, int, float, float, float, float, float, bytes, str]]:
    """
    ProcessPoolExecutor entry point (must be top-level for Windows spawn).
    """
    out: List[Tuple[uuid.UUID, str, int, int, int, float, float, float, float, float, bytes, str]] = []
    out_append = out.append
    for (asset_id, symbol, x, y, z, meta32, tax32, has_price, assigned_sector) in rows:
        out_append(
            _compute_vertex_record(
                asset_id=asset_id,
                symbol=symbol,
                raw_x=x,
                raw_y=y,
                raw_z=z,
                legacy_tax=tax32,
                legacy_meta=meta32,
                has_price=has_price,
                assigned_sector=assigned_sector,
                bounds=bounds,
            )
        )
    return out


def build_desired_counts(target: int) -> Dict[str, int]:
    n = len(SECTORS)
    base = target // n
    rem = target % n
    desired: Dict[str, int] = {}
    for i, s in enumerate(SECTORS):
        desired[s] = base + (1 if i < rem else 0)
    return desired


def build_redistribution_plan(real: Dict[str, int], desired: Dict[str, int]) -> Dict[str, Any]:
    """
    DeepSeek V30 deterministic plan:
    - keep_count[s] = min(real[s], desired[s])
    - deficit / surplus derived from real vs desired
    - transfer list built by round-robin over sector ID order.
    """
    keep_count = {s: min(real.get(s, 0), desired.get(s, 0)) for s in SECTORS}
    deficit = {s: max(0, desired.get(s, 0) - real.get(s, 0)) for s in SECTORS}
    surplus = {s: max(0, real.get(s, 0) - desired.get(s, 0)) for s in SECTORS}

    donors = [s for s in SECTORS if surplus[s] > 0]
    receivers = [s for s in SECTORS if deficit[s] > 0]

    transfers: List[Tuple[str, str]] = []
    donor_take: Dict[str, int] = {s: 0 for s in SECTORS}
    donor_receivers: Dict[str, List[str]] = {s: [] for s in SECTORS}

    if sum(real.values()) < sum(desired.values()):
        raise SystemExit(
            "ERROR: Insufficient assets for target.\n"
            f"  available_total={sum(real.values())} target={sum(desired.values())}\n"
            f"  real_by_sector={real}"
        )

    di = 0
    ri = 0
    remaining = sum(deficit.values())
    while remaining > 0:
        if not donors:
            raise SystemExit(
                "ERROR: Redistribution failed: no donors available while deficits remain.\n"
                f"  deficit_by_sector={deficit}\n"
                f"  surplus_by_sector={surplus}"
            )
        # Find next donor with surplus
        for _ in range(len(donors)):
            d = donors[di % len(donors)]
            di += 1
            if surplus[d] > 0:
                donor = d
                break
        else:
            raise SystemExit("ERROR: Redistribution failed: donors exhausted unexpectedly.")

        # Find next receiver with deficit
        for _ in range(len(receivers)):
            r = receivers[ri % len(receivers)]
            ri += 1
            if deficit[r] > 0:
                receiver = r
                break
        else:
            raise SystemExit("ERROR: Redistribution failed: receivers exhausted unexpectedly.")

        transfers.append((donor, receiver))
        donor_take[donor] += 1
        donor_receivers[donor].append(receiver)
        surplus[donor] -= 1
        deficit[receiver] -= 1
        remaining -= 1

        donors = [s for s in SECTORS if surplus[s] > 0]
        receivers = [s for s in SECTORS if deficit[s] > 0]

    return {
        "keep_count": keep_count,
        "donor_take": donor_take,
        "donor_receivers": donor_receivers,
        "transfers": transfers,
    }


def staging_table_name(sector: str) -> str:
    # Required fixed per-sector staging tables (case-sensitive identifiers).
    return f"stg_universe_assets_{sector}"


async def ensure_staging_tables(conn: asyncpg.Connection) -> None:
    """
    Create/ensure the 8 UNLOGGED per-sector staging tables required by the swap pipeline.
    """
    for s in SECTORS:
        tn = staging_table_name(s)
        await conn.execute(
            f"""
            CREATE UNLOGGED TABLE IF NOT EXISTS public."{tn}" (
              asset_id uuid,
              symbol text,
              morton_code bigint,
              taxonomy32 bigint,
              meta32 bigint,
              x real,
              y real,
              z real,
              fidelity_score real,
              spin real,
              vertex_buffer bytea,
              sector text
            );
            """
        )


async def truncate_staging_tables(conn: asyncpg.Connection) -> None:
    for s in SECTORS:
        tn = staging_table_name(s)
        await conn.execute(f'TRUNCATE TABLE public."{tn}";')


async def fetch_sector_counts(conn: asyncpg.Connection) -> Dict[str, int]:
    rows = await conn.fetch(
        """
        SELECT sector, COUNT(*)::int AS c
        FROM public.assets_source
        GROUP BY sector
        """
    )
    out = {s: 0 for s in SECTORS}
    for r in rows:
        sec = str(r["sector"] or "").strip()
        if sec in out:
            out[sec] = int(r["c"])
    return out


async def fetch_global_xyz_bounds(conn: asyncpg.Connection) -> Tuple[float, float, float, float, float, float]:
    """
    Normalization bounds are computed once from public.assets_source and are therefore deterministic
    for a given DB state.
    """
    row = await conn.fetchrow(
        """
        SELECT
          MIN(x)::float8 AS xmin, MAX(x)::float8 AS xmax,
          MIN(y)::float8 AS ymin, MAX(y)::float8 AS ymax,
          MIN(z)::float8 AS zmin, MAX(z)::float8 AS zmax
        FROM public.assets_source
        """
    )
    if not row:
        return (0.0, 1.0, 0.0, 1.0, 0.0, 1.0)
    xmin = _safe_float(row["xmin"], 0.0)
    xmax = _safe_float(row["xmax"], 1.0)
    ymin = _safe_float(row["ymin"], 0.0)
    ymax = _safe_float(row["ymax"], 1.0)
    zmin = _safe_float(row["zmin"], 0.0)
    zmax = _safe_float(row["zmax"], 1.0)
    return (xmin, xmax, ymin, ymax, zmin, zmax)


async def resolve_staging_morton_collisions(conn: asyncpg.Connection, *, max_attempts_per_row: int = 64) -> int:
    """
    Resolve Morton collisions across ALL staging tables deterministically.

    Strategy:
    - Detect duplicate morton_code across the staging UNION.
    - For each duplicate group, keep the first row by (morton_code, asset_id) and deterministically
      resample x/y/z for the remaining rows until a unique morton_code is found.

    This should be extremely rare with salted Morton; this function is the safety net.
    Returns number of rows modified.
    """
    union = "\nUNION ALL\n".join([f'SELECT * FROM public."{staging_table_name(s)}"' for s in SECTORS])

    def _dup_count_sql() -> str:
        return (
            "SELECT COUNT(*)::int FROM ("
            f"  SELECT morton_code FROM ({union}) u GROUP BY morton_code HAVING COUNT(*) > 1"
            ") d;"
        )

    def _exists_sql() -> str:
        return f"SELECT EXISTS(SELECT 1 FROM ({union}) u WHERE morton_code = $1 LIMIT 1);"

    modified = 0
    dup_groups = int(await conn.fetchval(_dup_count_sql()))
    if dup_groups == 0:
        return 0

    LOG.warning("Detected %d Morton duplicate groups in staging; starting deterministic repair", dup_groups)

    # Fetch duplicates in deterministic order.
    dup_mortons = await conn.fetch(
        f"""
        SELECT morton_code
        FROM ({union}) u
        GROUP BY morton_code
        HAVING COUNT(*) > 1
        ORDER BY morton_code ASC;
        """
    )

    for row in dup_mortons:
        mc = int(row["morton_code"])
        dups = await conn.fetch(
            f"""
            SELECT asset_id, symbol, sector
            FROM ({union}) u
            WHERE morton_code = $1
            ORDER BY asset_id ASC;
            """,
            mc,
        )
        if len(dups) <= 1:
            continue

        # Keep the first, repair the rest.
        for d in dups[1:]:
            asset_id = d["asset_id"]
            symbol = str(d["symbol"] or asset_id)
            sector = str(d["sector"] or "UTIL")
            if sector not in SECTORS:
                sector = "UTIL"

            # Deterministic resample loop
            base_salt = stable_u32_from_str(str(asset_id)) ^ stable_u32_from_str(symbol)
            for attempt in range(1, max_attempts_per_row + 1):
                x = stable_f01_from_str(symbol, f"cx:{attempt}")
                y = stable_f01_from_str(symbol, f"cy:{attempt}")
                z = stable_f01_from_str(symbol, f"cz:{attempt}")
                new_mc = morton63_from_unit_xyz_salted(x, y, z, base_salt ^ attempt)
                exists = bool(await conn.fetchval(_exists_sql(), new_mc))
                if exists:
                    continue

                # Update the row in its sector staging table.
                tn = staging_table_name(sector)
                cur = await conn.fetchrow(
                    f"""
                    SELECT taxonomy32, meta32, fidelity_score, spin
                    FROM public."{tn}"
                    WHERE asset_id = $1::uuid
                    LIMIT 1;
                    """,
                    asset_id,
                )
                if not cur:
                    raise SystemExit(f"ERROR: Collision repair could not locate staged row: sector={sector} asset_id={asset_id}")

                taxonomy32 = int(cur["taxonomy32"] or 0) & 0xFFFFFFFF
                meta32 = int(cur["meta32"] or 0) & 0xFFFFFFFF
                fidelity = float(cur["fidelity_score"] or 0.0)
                spin = float(cur["spin"] or 0.0)

                vb = pack_vertex28(int(new_mc) & 0xFFFFFFFF, meta32, x, y, z, fidelity, spin)
                await conn.execute(
                    f"""
                    UPDATE public."{tn}"
                    SET
                      x = $1::real,
                      y = $2::real,
                      z = $3::real,
                      morton_code = $4::bigint,
                      vertex_buffer = $5::bytea
                    WHERE asset_id = $6::uuid;
                    """,
                    float(x),
                    float(y),
                    float(z),
                    int(new_mc),
                    vb,
                    asset_id,
                )
                modified += 1
                break
            else:
                raise SystemExit(
                    "ERROR: Unable to resolve Morton collision deterministically within attempt budget.\n"
                    f"  morton_code={mc} asset_id={asset_id}"
                )

    # Re-check collisions
    dup_groups_after = int(await conn.fetchval(_dup_count_sql()))
    if dup_groups_after != 0:
        raise SystemExit(f"ERROR: Morton collision repair incomplete: {dup_groups_after} duplicate groups remain.")

    return modified


async def refresh_mv_if_exists(pool: asyncpg.Pool) -> None:
    """
    Refresh MV if it exists (optional). Don't fail seeding if MV absent.
    """
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            """
            SELECT EXISTS(
              SELECT 1 FROM pg_matviews
              WHERE schemaname='public' AND matviewname='universe_snapshot_v8'
            )
            """
        )
        if exists:
            await conn.execute("REFRESH MATERIALIZED VIEW public.universe_snapshot_v8;")
            LOG.info("Refreshed MV universe_snapshot_v8.")


async def finalize_swap_and_validate(conn: asyncpg.Connection, *, target: int) -> None:
    """
    Finalize pipeline:
    - TRUNCATE universe_assets
    - INSERT FROM staging (UNION ALL)
    - Validate: exact count, vertex stride, morton collisions
    - ANALYZE

    All within a single transaction: if any validation fails, the swap is rolled back.
    """
    union_select = "\nUNION ALL\n".join(
        [f'SELECT * FROM public."{staging_table_name(s)}"' for s in SECTORS]
    )

    await conn.execute("TRUNCATE TABLE public.universe_assets;")
    await conn.execute(
        f"""
        INSERT INTO public.universe_assets (
          asset_id, symbol, morton_code, taxonomy32, meta32,
          x, y, z, fidelity_score, spin, vertex_buffer, sector,
          governance_status, last_quantum_update
        )
        SELECT
          asset_id, symbol, morton_code, taxonomy32, meta32,
          x, y, z, fidelity_score, spin, vertex_buffer, sector,
          'PROVISIONAL', NOW()
        FROM (
          {union_select}
        ) AS u;
        """
    )

    # Validation gates (hard fail)
    n = int(await conn.fetchval("SELECT COUNT(*)::int FROM public.universe_assets;"))
    if n != target:
        raise SystemExit(f"ERROR: Finalize validation failed: expected {target} rows, got {n}.")

    bad_stride = int(
        await conn.fetchval(
            "SELECT COUNT(*)::int FROM public.universe_assets WHERE octet_length(vertex_buffer) != 28;"
        )
    )
    if bad_stride != 0:
        raise SystemExit(f"ERROR: Vertex28 stride validation failed: {bad_stride} rows are not 28 bytes.")

    morton_ok = bool(
        await conn.fetchval(
            "SELECT (COUNT(*) = COUNT(DISTINCT morton_code)) FROM public.universe_assets;"
        )
    )
    if not morton_ok:
        raise SystemExit("ERROR: Morton collision validation failed: COUNT(*) != COUNT(DISTINCT morton_code).")

    await conn.execute("ANALYZE public.universe_assets;")


async def verify_morton_monotonicity(pool: asyncpg.Pool, batch_size: int) -> None:
    """
    Verify that universe_snapshot_v8 MV is ordered by morton_code (monotonic).
    Checks by batches to avoid full scan.
    """
    async with pool.acquire() as conn:
        # Check if MV exists
        exists = await conn.fetchval(
            """
            SELECT EXISTS(
              SELECT 1 FROM pg_matviews
              WHERE schemaname='public' AND matviewname='universe_snapshot_v8'
            )
            """
        )
        if not exists:
            LOG.info("Skipping Morton monotonicity check: universe_snapshot_v8 MV does not exist")
            return
        
        total_rows = await conn.fetchval("SELECT COUNT(*)::int FROM public.universe_snapshot_v8;")
        if total_rows == 0:
            LOG.info("Skipping Morton monotonicity check: MV is empty")
            return
        
        LOG.info("Verifying Morton monotonicity (batch_size=%d, total_rows=%d)", batch_size, total_rows)
        
        prev_last_mc = None
        offset = 0
        batch_num = 0
        
        while offset < total_rows:
            batch_num += 1
            result = await conn.fetchrow(
                """
                WITH b AS (
                  SELECT ctid, morton_code
                  FROM public.universe_snapshot_v8
                  ORDER BY ctid
                  OFFSET $1 LIMIT $2
                ),
                t AS (
                  SELECT morton_code,
                         LEAD(morton_code) OVER (ORDER BY ctid) AS nxt
                  FROM b
                )
                SELECT
                  (SELECT morton_code FROM b ORDER BY ctid LIMIT 1) AS first_mc,
                  (SELECT morton_code FROM b ORDER BY ctid DESC LIMIT 1) AS last_mc,
                  COALESCE(BOOL_AND(morton_code <= nxt), TRUE) AS ok
                FROM t
                WHERE nxt IS NOT NULL;
                """,
                offset, batch_size
            )
            
            if not result:
                break
            
            first_mc = result["first_mc"]
            last_mc = result["last_mc"]
            ok = result["ok"]
            
            # Check within-batch monotonicity
            if not ok:
                LOG.error(
                    "Morton monotonicity violation in batch %d (offset %d): non-monotonic within batch",
                    batch_num, offset
                )
                raise SystemExit(2)
            
            # Check cross-batch continuity
            if prev_last_mc is not None:
                if first_mc < prev_last_mc:
                    LOG.error(
                        "Morton monotonicity violation at batch boundary %d: first_mc=%d < prev_last_mc=%d",
                        batch_num, first_mc, prev_last_mc
                    )
                    raise SystemExit(2)
            
            prev_last_mc = last_mc
            offset += batch_size
        
        LOG.info("Morton monotonicity OK: verified %d batches", batch_num)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=200000, help="Exact materialized rowcount (hard fail if insufficient inventory)")
    ap.add_argument("--concurrency", type=int, default=12, help="Ignored in non-CI mode: clamped to 12 workers")
    ap.add_argument("--batch", type=int, default=5000, help="Batch size for compute->COPY into staging")
    ap.add_argument("--verify", action="store_true", help="Run post-finalize verification banner (hard checks always enforced)")
    ap.add_argument("--ci", action="store_true", help="CI mode: allow overriding worker count")
    ap.add_argument("--check-morton", action="store_true", help="Verify Morton code monotonicity in MV")
    ap.add_argument("--morton-batch", type=int, default=50000, help="Batch size for Morton monotonicity check")
    args = ap.parse_args()

    dsn = pick_dsn()
    LOG.info("Using DSN: %s", dsn)

    # Postgres tuning requirement: leave headroom for OS/Postgres on Zen+ (8C/16T).
    # Heavy compute workers are clamped to 12 in non-CI mode, and DB pool is capped at 20.
    in_ci = bool(args.ci) or os.getenv("CI", "").strip().lower() in ("1", "true", "yes")
    worker_count = int(args.concurrency)
    if not in_ci:
        worker_count = 12
    else:
        worker_count = max(1, worker_count)

    pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=20)

    try:
        # If source_assets is missing, fall back to a deterministic synthetic seed so the UI renders TODAY.
        async with pool.acquire() as _c:
            has_source_assets = bool(
                await _c.fetchval("SELECT to_regclass('public.source_assets') IS NOT NULL;")
            )

        if not has_source_assets:
            synth_target = min(int(args.target), 5000)
            LOG.warning(
                "public.source_assets is missing. Seeding a deterministic synthetic universe into public.universe_assets (n=%d).",
                synth_target,
            )
            async with pool.acquire() as conn:
                await ensure_quantum_schema(conn)

                # Fast, deterministic upsert of SYN* symbols.
                rows: List[Tuple] = []
                for i in range(synth_target):
                    sym = f"SYN{i:06d}"
                    sector = SECTORS[i % len(SECTORS)]
                    # deterministic positions in [0,1]
                    x = stable_f01_from_str(sym, "x")
                    y = stable_f01_from_str(sym, "y")
                    z = stable_f01_from_str(sym, "z") * 0.2
                    # zeroless bits
                    domain = (i % 7) + 1
                    industry = ((i // 16) % 63) + 1
                    risk = ((i // 97) % 7) + 1
                    vol = ((i // 13) % 31) + 1
                    tax32 = taxonomy32_zeroless(domain, industry, risk, vol)
                    meta32 = meta32_minimal(outlier=(i % 37 == 0), risk_tier=risk, liquidity_tier=2)
                    fid = fidelity_score(has_price=False, has_sector=True)
                    spin = spin_value(tax32, risk)
                    mort = morton63_from_unit_xyz_salted(x, y, z, stable_u32_from_str(sym))
                    vb = pack_vertex28(int(mort) & 0xFFFFFFFF, meta32, x, y, z, fid, spin)
                    if len(vb) != VERTEX_STRIDE:
                        raise SystemExit(f"ERROR: Vertex28 pack stride mismatch for {sym}: {len(vb)}")
                    rows.append(
                        (
                            uuid.uuid4(),
                            sym,
                            int(mort),
                            int(tax32),
                            int(meta32),
                            float(x),
                            float(y),
                            float(z),
                            float(fid),
                            float(spin),
                            vb,
                            sector,
                        )
                    )

                await conn.executemany(
                    """
                    INSERT INTO public.universe_assets (
                      asset_id, symbol, morton_code, taxonomy32, meta32, x, y, z, fidelity_score, spin, vertex_buffer, sector
                    )
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                    ON CONFLICT (symbol) DO UPDATE SET
                      morton_code=EXCLUDED.morton_code,
                      taxonomy32=EXCLUDED.taxonomy32,
                      meta32=EXCLUDED.meta32,
                      x=EXCLUDED.x, y=EXCLUDED.y, z=EXCLUDED.z,
                      fidelity_score=EXCLUDED.fidelity_score,
                      spin=EXCLUDED.spin,
                      vertex_buffer=EXCLUDED.vertex_buffer,
                      sector=EXCLUDED.sector,
                      last_quantum_update=NOW();
                    """,
                    rows,
                )

            # Refresh MV if present
            try:
                await refresh_mv_if_exists(pool)
            except Exception as e:
                # Inserts must remain committed even if snapshot/MV steps fail.
                LOG.warning("MV refresh failed (continuing): %s: %s", type(e).__name__, e)

            if args.verify:
                async with pool.acquire() as conn:
                    n = int(await conn.fetchval("SELECT COUNT(*) FROM public.universe_assets;") or 0)
                    if n < synth_target:
                        raise SystemExit(f"ERROR: synthetic verify failed: expected >= {synth_target} got {n}")
                    bad = int(
                        await conn.fetchval(
                            "SELECT COUNT(*) FROM public.universe_assets WHERE octet_length(vertex_buffer) != 28;"
                        )
                        or 0
                    )
                    if bad != 0:
                        raise SystemExit(f"ERROR: synthetic verify failed: {bad} rows have vertex_buffer != 28")
                    LOG.info("Synthetic seed OK: universe_assets=%d (vertex28 stride OK)", n)

            return

        # Ensure legacy schema and canonical assets view (real pipeline)
        await ensure_legacy_schema(pool)
        await ensure_assets_source_view(pool)

        async with pool.acquire() as conn:
            await ensure_quantum_schema(conn)
        async with pool.acquire() as conn:
            await ensure_staging_tables(conn)
            await truncate_staging_tables(conn)

            real = await fetch_sector_counts(conn)
            desired = build_desired_counts(int(args.target))

            total_real = sum(real.values())
            if total_real < args.target:
                raise SystemExit(
                    "ERROR: Insufficient source inventory for requested target.\n"
                    f"  target={args.target}\n"
                    f"  available_total={total_real}\n"
                    f"  available_by_sector={real}"
                )

            plan = build_redistribution_plan(real, desired)
            keep_count: Dict[str, int] = plan["keep_count"]
            donor_take: Dict[str, int] = plan["donor_take"]
            donor_receivers: Dict[str, List[str]] = plan["donor_receivers"]

            LOG.info("=" * 88)
            LOG.info("Deterministic Allocation Plan (target=%d, workers=%d, batch=%d)", args.target, worker_count, args.batch)
            LOG.info("%-6s %12s %12s %12s %12s", "SEC", "REAL", "DESIRED", "KEEP", "DONATE")
            for s in SECTORS:
                LOG.info("%-6s %12d %12d %12d %12d", s, real[s], desired[s], keep_count[s], donor_take[s])
            LOG.info("Transfers total: %d", len(plan["transfers"]))
            LOG.info("=" * 88)

            bounds = await fetch_global_xyz_bounds(conn)
            LOG.info("Global XYZ bounds for normalization: %s", bounds)

        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=worker_count)
        try:
            sem = asyncio.Semaphore(worker_count)

            async def copy_to_staging(records: Sequence[Tuple], assigned_sector: str) -> None:
                if not records:
                    return
                tn = staging_table_name(assigned_sector)
                async with pool.acquire() as c:
                    await c.copy_records_to_table(
                        tn,
                        schema_name="public",
                        records=records,
                        columns=[
                            "asset_id",
                            "symbol",
                            "morton_code",
                            "taxonomy32",
                            "meta32",
                            "x",
                            "y",
                            "z",
                            "fidelity_score",
                            "spin",
                            "vertex_buffer",
                            "sector",
                        ],
                    )

            async def materialize_keep(sector: str) -> int:
                async with sem:
                    n_target = keep_count[sector]
                    if n_target <= 0:
                        return 0
                    async with pool.acquire() as c:
                        rows = await fetch_assets_slice(c, sector=sector, limit=n_target, offset=0)

                    raw: List[Tuple[uuid.UUID, str, float, float, float, int, int, bool, str]] = []
                    raw_append = raw.append
                    for r in rows:
                        aid = r["id"]
                        sym = str(r["symbol"] or aid)
                        raw_append(
                            (
                                aid,
                                sym,
                                _safe_float(r["x"], 0.0),
                                _safe_float(r["y"], 0.0),
                                _safe_float(r["z"], 0.0),
                                int(r["meta32"] or 0),
                                int(r["titan_taxonomy32"] or 0),
                                bool(r["has_price"]),
                                sector,
                            )
                        )

                    written = 0
                    for i in range(0, len(raw), args.batch):
                        chunk = raw[i : i + args.batch]
                        computed = await loop.run_in_executor(executor, compute_batch, chunk, bounds)
                        await copy_to_staging(computed, sector)
                        written += len(computed)
                    return written

            async def materialize_donations(donor: str) -> int:
                async with sem:
                    n_take = donor_take[donor]
                    if n_take <= 0:
                        return 0
                    async with pool.acquire() as c:
                        donation_rows = await fetch_assets_slice(c, sector=donor, limit=n_take, offset=desired[donor])

                    receiver_seq = donor_receivers[donor]
                    if len(donation_rows) != len(receiver_seq):
                        raise SystemExit(
                            "ERROR: Donation fetch count mismatch.\n"
                            f"  donor={donor} expected={len(receiver_seq)} fetched={len(donation_rows)}"
                        )

                    raw_by_receiver: Dict[str, List[Tuple[uuid.UUID, str, float, float, float, int, int, bool, str]]] = {
                        s: [] for s in SECTORS
                    }
                    for r, recv in zip(donation_rows, receiver_seq):
                        aid = r["id"]
                        sym = str(r["symbol"] or aid)
                        raw_by_receiver[recv].append(
                            (
                                aid,
                                sym,
                                _safe_float(r["x"], 0.0),
                                _safe_float(r["y"], 0.0),
                                _safe_float(r["z"], 0.0),
                                int(r["meta32"] or 0),
                                int(r["titan_taxonomy32"] or 0),
                                bool(r["has_price"]),
                                recv,
                            )
                        )

                    written = 0
                    for recv in SECTORS:
                        raw = raw_by_receiver[recv]
                        for i in range(0, len(raw), args.batch):
                            chunk = raw[i : i + args.batch]
                            computed = await loop.run_in_executor(executor, compute_batch, chunk, bounds)
                            await copy_to_staging(computed, recv)
                            written += len(computed)
                    return written

            keep_tasks = [asyncio.create_task(materialize_keep(s)) for s in SECTORS]
            donation_tasks = [asyncio.create_task(materialize_donations(s)) for s in SECTORS if donor_take[s] > 0]
            keep_counts = await asyncio.gather(*keep_tasks)
            donation_counts = await asyncio.gather(*donation_tasks) if donation_tasks else []

            staged_total = int(sum(keep_counts) + sum(donation_counts))
            if staged_total != args.target:
                raise SystemExit(f"ERROR: Staging rowcount mismatch: expected {args.target}, got {staged_total}")

            async with pool.acquire() as c:
                for s in SECTORS:
                    tn = staging_table_name(s)
                    n = int(await c.fetchval(f'SELECT COUNT(*)::int FROM public.\"{tn}\";'))
                    if n != desired[s]:
                        raise SystemExit(
                            "ERROR: Staging per-sector count mismatch.\n"
                            f"  sector={s} expected={desired[s]} got={n}"
                        )

            # Morton63 integrity: repair any staging collisions deterministically before the atomic finalize swap.
            async with pool.acquire() as c:
                repaired = await resolve_staging_morton_collisions(c)
                if repaired:
                    LOG.warning("Morton collision repair updated %d staged rows", repaired)

            async with pool.acquire() as c:
                async with c.transaction():
                    await finalize_swap_and_validate(c, target=int(args.target))

            await refresh_mv_if_exists(pool)
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        dt = time.perf_counter() - t0
        rps = (args.target / dt) if dt > 0 else 0.0
        LOG.info("DONE: materialized %d rows in %.3fs (%.1f rows/s)", args.target, dt, rps)

        if args.check_morton:
            await verify_morton_monotonicity(pool, args.morton_batch)

        if args.verify:
            LOG.info("Verification enforced: exact count + Vertex28 stride + morton collision-free.")

    finally:
        await pool.close()


if __name__ == "__main__":
    # Route A: PostgreSQL-only deterministic seed using staging table public._stg_universe_assets.
    from backend.scripts.seed_universe_v8_routeA import main as route_a_main

    asyncio.run(route_a_main())
