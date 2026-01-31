#!/usr/bin/env python3
"""
Stress seed: Generate 100,000 assets with clustered 32-bit taxonomy_id structure.
Creates 6 monolith domains with heavy clustering for visible "galaxy" structure.
"""
import argparse
import random
import hashlib
import sys
from pathlib import Path
from typing import List, Tuple
import numpy as np

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from database import SessionLocal, engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import time


def make_titan_taxonomy32(monolith: int, cluster: int, subcluster: int, variant: int) -> int:
    """
    Pack Titan taxonomy32 (8-8-8-8 layout for prefix indexing).
    
    Bit allocation (MSB → LSB):
    - [31..24]  B3 = (monolith<<5) | cluster_id (0..31)  [monolith in 0..5, cluster in 0..31]
    - [23..16]  B2 = subcluster (0..255)
    - [15..8]   B1 = category/temporal (0..255)
    - [7..0]    B0 = stable hash leaf (0..255)
    
    Prefix index: (titan & 0xFF000000) extracts monolith+cluster for O(1) lookups.
    """
    if not (0 <= monolith <= 5):
        raise ValueError(f"Monolith must be 0-5, got {monolith}")
    if not (0 <= cluster <= 31):
        raise ValueError(f"Cluster must be 0-31, got {cluster}")
    if not (0 <= subcluster <= 255):
        raise ValueError(f"Subcluster must be 0-255, got {subcluster}")
    if not (0 <= variant <= 255):
        raise ValueError(f"Variant must be 0-255, got {variant}")
    
    # B3 = (monolith<<5) | cluster (ensures prefix8 = monolith+cluster)
    b3 = ((monolith & 0x7) << 5) | (cluster & 0x1F)
    
    titan32 = (
        ((b3 & 0xFF) << 24) |
        ((subcluster & 0xFF) << 16) |
        ((variant & 0xFF) << 8) |
        (variant & 0xFF)  # B0 = variant (or hash leaf)
    )
    
    return titan32 & 0xFFFFFFFF


def make_meta32(risk8: int, shock8: int, temporal8: int, flags8: int) -> int:
    """
    Pack GPU meta word into 32-bit unsigned integer.
    
    Bit allocation (MSB → LSB):
    - [31..24]  RISK8     (8 bits) -> 0..255
    - [23..16]  SHOCK8    (8 bits) -> 0..255
    - [15..8]   TEMPORAL8 (8 bits) -> 0..255
    - [7..0]    FLAGS8    (8 bits) -> bit0: high_risk, bit1: in_shock, bit2: outlier
    """
    if not (0 <= risk8 <= 255):
        raise ValueError(f"Risk8 must be 0-255, got {risk8}")
    if not (0 <= shock8 <= 255):
        raise ValueError(f"Shock8 must be 0-255, got {shock8}")
    if not (0 <= temporal8 <= 255):
        raise ValueError(f"Temporal8 must be 0-255, got {temporal8}")
    if not (0 <= flags8 <= 255):
        raise ValueError(f"Flags8 must be 0-255, got {flags8}")
    
    meta32 = (
        ((risk8 & 0xFF) << 24) |
        ((shock8 & 0xFF) << 16) |
        ((temporal8 & 0xFF) << 8) |
        (flags8 & 0xFF)
    )
    
    return meta32 & 0xFFFFFFFF


def zipf_weights(n: int, s: float = 1.15) -> List[float]:
    """Generate Zipf-like weights normalized to sum to 1.0"""
    weights = [1.0 / (i ** s) for i in range(1, n + 1)]
    total = sum(weights)
    return [w / total for w in weights]


def weighted_choice(items: List, weights: List[float], rng) -> int:
    """Choose index from items using weights"""
    return rng.choices(range(len(items)), weights=weights, k=1)[0]


def make_cluster_centers(monolith: int, cluster: int, rng) -> Tuple[float, float]:
    """Generate deterministic center coordinates for (monolith, cluster)"""
    # Use monolith and cluster as seed for deterministic centers
    seed = monolith * 1000 + cluster
    local_rng = random.Random(seed)
    x = local_rng.uniform(0.1, 0.9)
    y = local_rng.uniform(0.1, 0.9)
    return (x, y)


def generate_clustered_assets(n_assets: int = 100000, seed: int = 1337) -> List[dict]:
    """
    Generate assets with clustered taxonomy_id distribution.
    
    Returns list of asset dicts with: symbol, name, taxonomy_id, x, y (optional coords)
    """
    rng = random.Random(seed)
    np.random.seed(seed)
    
    # Monolith weights (6 monoliths)
    monolith_weights = [0.20, 0.18, 0.17, 0.16, 0.15, 0.14]
    assert abs(sum(monolith_weights) - 1.0) < 1e-6, "Monolith weights must sum to 1.0"
    
    # Predefine cluster hubs per monolith (16-32 clusters each, max 127)
    monolith_clusters = {}
    for m in range(6):
        k_m = rng.randint(16, 32)
        monolith_clusters[m] = list(range(k_m))
    
    # Predefine subclusters per cluster (8-bit range: 0-255)
    subcluster_counts = {}
    for m in range(6):
        for c in monolith_clusters[m]:
            # Deterministic count per (monolith, cluster)
            seed = m * 1000 + c
            local_rng = random.Random(seed)
            subcluster_counts[(m, c)] = local_rng.randint(8, 64)
    
    assets = []
    taxonomy_ids = []
    
    for i in range(n_assets):
        # Sample monolith
        monolith = weighted_choice(list(range(6)), monolith_weights, rng)
        
        # Sample cluster within monolith (Zipf-like)
        clusters = monolith_clusters[monolith]
        cluster_weights = zipf_weights(len(clusters), s=1.15)
        cluster_idx = weighted_choice(clusters, cluster_weights, rng)
        cluster = clusters[cluster_idx]
        
        # Sample subcluster within cluster (also Zipf-like)
        n_subclusters = subcluster_counts[(monolith, cluster)]
        subcluster_weights_local = zipf_weights(n_subclusters, s=1.2)
        subcluster_idx = weighted_choice(list(range(n_subclusters)), subcluster_weights_local, rng)
        subcluster = min(subcluster_idx, 255)  # Clamp to 8-bit
        
        # Generate variant (correlated by subcluster seed)
        variant_seed = monolith * 10000 + cluster * 100 + subcluster_idx
        variant_rng = random.Random(variant_seed + i)
        variant = variant_rng.randint(0, 255)
        
        # Pack Titan taxonomy32 (prefix-friendly 8-8-8-8)
        titan_taxonomy32 = make_titan_taxonomy32(monolith, cluster, subcluster, variant)
        taxonomy_ids.append(titan_taxonomy32)
        
        # Generate coordinates (optional, for visible galaxies)
        center_x, center_y = make_cluster_centers(monolith, cluster, rng)
        
        # Determine jitter sigma based on cluster size
        cluster_size_approx = n_assets * monolith_weights[monolith] * cluster_weights[cluster_idx] / len(clusters)
        if cluster_size_approx > 1000:
            sigma = 0.01
        elif cluster_size_approx > 500:
            sigma = 0.015
        elif cluster_size_approx > 200:
            sigma = 0.02
        else:
            sigma = 0.03
        
        # Sample around center with gaussian jitter
        jitter_x = rng.gauss(0, sigma)
        jitter_y = rng.gauss(0, sigma)
        x = np.clip(center_x + jitter_x, 0.0, 1.0)
        y = np.clip(center_y + jitter_y, 0.0, 1.0)
        
        # Map to uint16 grid and pack
        x_uint16 = int(np.clip(x, 0, 1) * 65535)
        y_uint16 = int(np.clip(y, 0, 1) * 65535)
        posPacked = (x_uint16 << 16) | y_uint16
        
        # Generate canonical mask (domain/outlier/risk layout)
        from engines.bitmask_encoder import pack_taxonomy_mask
        
        # Risk correlated with cluster (higher risk in some clusters)
        risk_base = float((cluster % 32) * 8) / 255.0  # Normalize to [0,1]
        risk_jitter = rng.uniform(-0.05, 0.05)
        risk01 = np.clip(risk_base + risk_jitter, 0.0, 1.0)
        
        # Outlier flag (5% chance)
        outlier = 1 if rng.random() < 0.05 else 0
        
        # Pack canonical mask (domain/outlier/risk)
        canonical_mask = pack_taxonomy_mask(domain=monolith, outlier=outlier, risk01=risk01)
        
        # Generate meta32 with 4x8-bit lanes: risk8, shock8, temporal8, flags8
        risk8 = int(np.clip(risk01 * 255, 0, 255))
        # Shock8: correlated with cluster volatility (some clusters have higher shock)
        shock_base = float((cluster % 16) * 16) / 255.0  # 0-240 range
        shock_jitter = rng.uniform(-0.1, 0.1)
        shock01 = np.clip(shock_base + shock_jitter, 0.0, 1.0)
        shock8 = int(np.clip(shock01 * 255, 0, 255))
        # Temporal8: deterministic hash of taxonomy32 for phase offset
        temporal8 = (titan_taxonomy32 >> 8) & 0xFF
        # Flags8: bit0=high_risk, bit1=in_shock, bit2=outlier
        flags8 = 0
        if risk8 >= 200:
            flags8 |= 0x01  # high_risk
        if shock8 >= 200:
            flags8 |= 0x02  # in_shock
        if outlier:
            flags8 |= 0x04  # outlier
        meta32 = make_meta32(risk8, shock8, temporal8, flags8)
        
        # Generate symbol and name
        symbol = f"SYN{i:06d}"
        name = f"Asset-{i+1}"
        
        assets.append({
            'symbol': symbol,
            'name': name,
            'titan_taxonomy32': titan_taxonomy32,
            'canonical_mask_u32': int(canonical_mask),
            'meta32': meta32,
            'posPacked': posPacked,
            'x': x_uint16,
            'y': y_uint16,
            'monolith': monolith,
            'cluster': cluster,
            'subcluster': subcluster
        })
    
    return assets, taxonomy_ids


def validate_distribution(assets: List[dict], taxonomy_ids: List[int], sample_size: int = 10000):
    """Print validation statistics for taxonomy_id distribution"""
    sample = taxonomy_ids[:sample_size] if len(taxonomy_ids) > sample_size else taxonomy_ids
    
    # Extract monolith counts
    monolith_counts = {}
    cluster_freq = {}
    subcluster_freq = {}
    
    for tid in sample:
        # Extract from Titan layout: B3 = (monolith<<5) | cluster
        b3 = (tid >> 24) & 0xFF
        monolith = (b3 >> 5) & 0x7
        cluster = b3 & 0x1F
        subcluster = (tid >> 16) & 0xFF
        
        monolith_counts[monolith] = monolith_counts.get(monolith, 0) + 1
        key = (monolith, cluster)
        cluster_freq[key] = cluster_freq.get(key, 0) + 1
        key2 = (monolith, cluster, subcluster)
        subcluster_freq[key2] = subcluster_freq.get(key2, 0) + 1
    
    print(f"\n=== Validation (sample of {len(sample)} taxonomy_ids) ===")
    print("\nMonolith distribution:")
    for m in sorted(monolith_counts.keys()):
        count = monolith_counts[m]
        pct = 100.0 * count / len(sample)
        print(f"  Monolith {m}: {count:6d} ({pct:5.2f}%)")
    
    print("\nTop 10 clusters by frequency:")
    sorted_clusters = sorted(cluster_freq.items(), key=lambda x: x[1], reverse=True)[:10]
    for (m, c), freq in sorted_clusters:
        print(f"  Monolith {m}, Cluster {c:2d}: {freq:6d}")
    
    print(f"\nDistinct (monolith, cluster, subcluster) count: {len(subcluster_freq)}")
    print(f"Total distinct clusters: {len(cluster_freq)}")
    print("=" * 50)


def batch_insert_assets_postgres(assets: List[dict], db_url: str, batch_size: int = 10000):
    """Insert assets into Postgres using asyncpg"""
    try:
        import asyncpg
    except ImportError:
        raise ImportError("asyncpg required for Postgres. Install: pip install asyncpg")
    
    import asyncio
    
    async def _insert():
        conn = await asyncpg.connect(db_url)
        try:
            # Check/add columns
            await conn.execute("""
                ALTER TABLE assets 
                ADD COLUMN IF NOT EXISTS titan_taxonomy32 BIGINT,
                ADD COLUMN IF NOT EXISTS canonical_mask_u32 BIGINT,
                ADD COLUMN IF NOT EXISTS meta32 BIGINT,
                ADD COLUMN IF NOT EXISTS posPacked BIGINT,
                ADD COLUMN IF NOT EXISTS x INTEGER,
                ADD COLUMN IF NOT EXISTS y INTEGER
            """)
            
            # Create indexes
            await conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_titan_taxonomy32 ON assets(titan_taxonomy32)")
            await conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_canonical_mask ON assets(canonical_mask_u32)")
            await conn.execute("CREATE INDEX IF NOT EXISTS ix_assets_posPacked ON assets(posPacked)")
            
            # Batch insert
            for i in range(0, len(assets), batch_size):
                chunk = assets[i:i+batch_size]
                values = [
                    (a['symbol'], a['name'], True, a['titan_taxonomy32'], a['canonical_mask_u32'], a['meta32'], a['posPacked'], a['x'], a['y'])
                    for a in chunk
                ]
                await conn.executemany("""
                    INSERT INTO assets (symbol, name, is_active, titan_taxonomy32, canonical_mask_u32, meta32, posPacked, x, y)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, values)
                print(f"Inserted batch {i // batch_size + 1} ({len(chunk)} assets)")
        finally:
            await conn.close()
    
    asyncio.run(_insert())


def batch_insert_assets(engine_or_conn, assets: List[dict], batch_size: int = 5000):
    """Insert assets in batches (SQLite)"""
    from config import settings
    
    # Check if Postgres
    if 'postgresql://' in settings.DATABASE_URL or 'postgres://' in settings.DATABASE_URL:
        print("Detected Postgres database, using asyncpg...")
        batch_insert_assets_postgres(assets, settings.DATABASE_URL, batch_size=min(batch_size, 10000))
        return
    
    # SQLite path
    with engine_or_conn.connect() as chk:
        try:
            cols = chk.execute(text("PRAGMA table_info(assets)")).mappings().all()
            existing_cols = {c['name'] for c in cols}
        except:
            # Not SQLite, try Postgres schema check
            cols = chk.execute(text("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'assets'
            """)).mappings().all()
            existing_cols = {c['column_name'] for c in cols}
        
        if 'titan_taxonomy32' not in existing_cols:
            print("Adding titan_taxonomy32, canonical_mask_u32, meta32, posPacked columns to assets table...")
            try:
                chk.execute(text("ALTER TABLE assets ADD COLUMN titan_taxonomy32 INTEGER"))
                chk.execute(text("ALTER TABLE assets ADD COLUMN canonical_mask_u32 INTEGER"))
                chk.execute(text("ALTER TABLE assets ADD COLUMN meta32 INTEGER"))
                chk.execute(text("ALTER TABLE assets ADD COLUMN posPacked INTEGER"))
            except:
                chk.execute(text("ALTER TABLE assets ADD COLUMN titan_taxonomy32 BIGINT"))
                chk.execute(text("ALTER TABLE assets ADD COLUMN canonical_mask_u32 BIGINT"))
                chk.execute(text("ALTER TABLE assets ADD COLUMN meta32 BIGINT"))
                chk.execute(text("ALTER TABLE assets ADD COLUMN posPacked BIGINT"))
            chk.commit()
        
        if 'x' not in existing_cols:
            print("Adding x, y coordinate columns to assets table...")
            chk.execute(text("ALTER TABLE assets ADD COLUMN x INTEGER"))
            chk.execute(text("ALTER TABLE assets ADD COLUMN y INTEGER"))
            chk.commit()
    
    # Build insert statement
    insert_cols = ['symbol', 'name', 'is_active', 'titan_taxonomy32', 'canonical_mask_u32', 'meta32', 'posPacked', 'x', 'y']
    col_placeholders = ', '.join(insert_cols)
    param_placeholders = ', '.join([f":{c}" for c in insert_cols])
    insert_sql = text(f"INSERT INTO assets ({col_placeholders}) VALUES ({param_placeholders})")
    
    for i in range(0, len(assets), batch_size):
        chunk = assets[i:i+batch_size]
        params = []
        for asset in chunk:
            params.append({
                'symbol': asset['symbol'],
                'name': asset['name'],
                'is_active': 1,
                'titan_taxonomy32': asset['titan_taxonomy32'],
                'canonical_mask_u32': asset['canonical_mask_u32'],
                'meta32': asset['meta32'],
                'posPacked': asset['posPacked'],
                'x': asset['x'],
                'y': asset['y']
            })
        
        retries = 5
        backoff = 0.2
        for attempt in range(retries):
            try:
                with engine_or_conn.begin() as trans_conn:
                    trans_conn.execute(insert_sql, params)
                print(f"Inserted batch {i // batch_size + 1} ({len(chunk)} assets)")
                break
            except OperationalError as e:
                if 'database is locked' in str(e).lower() and attempt < retries - 1:
                    wait = backoff * (2 ** attempt)
                    print(f"Database is locked, retrying batch {i // batch_size + 1} in {wait:.2f}s")
                    time.sleep(wait)
                    continue
                raise


def main():
    from config import settings
    
    parser = argparse.ArgumentParser(description='Seed 100,000 assets with clustered Titan taxonomy32')
    parser.add_argument('--n', '--n-assets', type=int, default=100000, dest='n_assets', help='Number of assets to generate')
    parser.add_argument('--seed', type=int, default=1337, help='Random seed for reproducibility')
    parser.add_argument('--reset', action='store_true', help='Delete existing assets before seeding')
    parser.add_argument('--batch-size', type=int, default=10000, help='Batch size for inserts')
    parser.add_argument('--validate-only', action='store_true', help='Only validate, do not insert')
    args = parser.parse_args()
    
    # Check database type
    is_postgres = 'postgresql://' in settings.DATABASE_URL or 'postgres://' in settings.DATABASE_URL
    is_sqlite = 'sqlite://' in settings.DATABASE_URL.lower()
    
    if is_sqlite and args.n_assets > 10000:
        print("WARNING: SQLite detected. Large inserts (>10k) may be slow. Consider using Postgres.")
    
    if not is_postgres and not is_sqlite:
        print(f"ERROR: Unsupported database URL format: {settings.DATABASE_URL}")
        print("Expected postgresql:// or sqlite://")
        return
    
    print(f"Generating {args.n_assets} assets with clustered Titan taxonomy32 (seed={args.seed})...")
    assets, taxonomy_ids = generate_clustered_assets(n_assets=args.n_assets, seed=args.seed)
    
    # Validate distribution
    validate_distribution(assets, taxonomy_ids, sample_size=min(10000, len(taxonomy_ids)))
    
    if args.validate_only:
        print("\nValidation complete (--validate-only, skipping insert)")
        return
    
    # Reset if requested
    if args.reset:
        print("\nResetting assets table...")
        if is_postgres:
            try:
                import asyncpg
                import asyncio
                async def _reset():
                    conn = await asyncpg.connect(settings.DATABASE_URL)
                    await conn.execute("DELETE FROM assets")
                    await conn.close()
                asyncio.run(_reset())
            except ImportError:
                print("asyncpg not installed, using SQLAlchemy for reset...")
                with engine.connect() as conn:
                    conn.execute(text("DELETE FROM assets"))
                    conn.commit()
        else:
            with engine.connect() as conn:
                conn.execute(text("DELETE FROM assets"))
                conn.commit()
    
    # Insert assets
    print(f"\nInserting {len(assets)} assets in batches of {args.batch_size}...")
    batch_insert_assets(engine, assets, batch_size=args.batch_size)
    
    print("\nSeeding complete!")


if __name__ == '__main__':
    main()
