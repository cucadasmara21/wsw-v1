"""
Synthetic "Galaxy" Fallback Seeding System

Generates 10,000 assets distributed in 6 Gaussian clusters (Risk Domains)
if the database is empty. Idempotent: exits silently if assets exist.
"""
from __future__ import annotations

import logging
import random

from sqlalchemy import text
from sqlalchemy.engine import Engine

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

logger = logging.getLogger(__name__)

# 6 Risk Domain Cluster Centroids (spread across [0,1] x [0,1])
CLUSTER_CENTROIDS = [
    (0.2, 0.2),  # Cluster 1: Credit Risk
    (0.8, 0.2),  # Cluster 2: Market Risk
    (0.2, 0.8),  # Cluster 3: Liquidity Risk
    (0.8, 0.8),  # Cluster 4: Operational Risk
    (0.5, 0.1),  # Cluster 5: Systemic Risk
    (0.5, 0.9),  # Cluster 6: Regulatory Risk
]

CLUSTER_STD_DEV = 0.05  # Standard deviation for Gaussian distribution
TOTAL_ASSETS = 10000
ASSETS_PER_CLUSTER = TOTAL_ASSETS // len(CLUSTER_CENTROIDS)


def _generate_coordinates_gaussian(centroid_x: float, centroid_y: float, count: int) -> list[tuple[float, float]]:
    """Generate coordinates using Gaussian distribution around centroid"""
    if HAS_NUMPY:
        x_coords = np.random.normal(centroid_x, CLUSTER_STD_DEV, count)
        y_coords = np.random.normal(centroid_y, CLUSTER_STD_DEV, count)
        # Clamp to [0, 1]
        x_coords = np.clip(x_coords, 0.0, 1.0)
        y_coords = np.clip(y_coords, 0.0, 1.0)
        return list(zip(x_coords.tolist(), y_coords.tolist()))
    else:
        # Fallback to random.gauss
        coords = []
        for _ in range(count):
            x = random.gauss(centroid_x, CLUSTER_STD_DEV)
            y = random.gauss(centroid_y, CLUSTER_STD_DEV)
            x = max(0.0, min(1.0, x))
            y = max(0.0, min(1.0, y))
            coords.append((x, y))
        return coords


def _pack_meta32(risk: int = 0, shock: int = 0, trend: int = 0, vitality: int = 0) -> int:
    """
    Pack meta32: bits 24-31=risk, 16-23=shock, 8-15=trend, 0-7=vitality
    All values clamped to 0-255
    """
    risk = max(0, min(255, risk))
    shock = max(0, min(255, shock))
    trend = max(0, min(255, trend))
    vitality = max(0, min(255, vitality))
    return (risk << 24) | (shock << 16) | (trend << 8) | vitality


def seed_if_empty(engine: Engine) -> bool:
    """
    Seed 10,000 synthetic assets in 6 clusters if database is empty.
    Returns True if seeding occurred, False if skipped (already has data).
    """
    try:
        with engine.connect() as conn:
            # Idempotency check
            result = conn.execute(text("SELECT COUNT(*) AS n FROM assets")).mappings().first()
            count = int(result["n"]) if result and result.get("n") is not None else 0
            
            if count > 0:
                logger.info(f"seed_titan_fallback: Database has {count} assets, skipping seed")
                return False
            
            logger.info("seed_titan_fallback: Database empty, generating 10,000 synthetic assets...")
            
            # Generate assets for each cluster
            all_assets = []
            asset_idx = 0
            
            for cluster_id, (centroid_x, centroid_y) in enumerate(CLUSTER_CENTROIDS, start=1):
                coords = _generate_coordinates_gaussian(centroid_x, centroid_y, ASSETS_PER_CLUSTER)
                
                for x, y in coords:
                    asset_idx += 1
                    symbol = f"SYN{asset_idx:05d}"
                    name = f"Synthetic Asset {asset_idx} (Cluster {cluster_id})"
                    
                    # Random meta32: vitality in bits 0-7, trend/shock/risk in upper bits
                    vitality = random.randint(0, 255)
                    trend = random.randint(0, 255)
                    shock = random.randint(0, 255)
                    risk = random.randint(0, 255)
                    meta32 = _pack_meta32(risk=risk, shock=shock, trend=trend, vitality=vitality)
                    
                    # titan_taxonomy32 = cluster_id (1-6)
                    titan_taxonomy32 = cluster_id & 0xFFFFFFFF
                    
                    all_assets.append({
                        "symbol": symbol,
                        "name": name,
                        "x": x,
                        "y": y,
                        "titan_taxonomy32": titan_taxonomy32,
                        "meta32": meta32,
                    })
            
            # Handle remainder if TOTAL_ASSETS not perfectly divisible
            remainder = TOTAL_ASSETS - len(all_assets)
            if remainder > 0:
                last_cluster_coords = _generate_coordinates_gaussian(
                    CLUSTER_CENTROIDS[-1][0],
                    CLUSTER_CENTROIDS[-1][1],
                    remainder
                )
                for x, y in last_cluster_coords:
                    asset_idx += 1
                    symbol = f"SYN{asset_idx:05d}"
                    name = f"Synthetic Asset {asset_idx} (Cluster {len(CLUSTER_CENTROIDS)})"
                    vitality = random.randint(0, 255)
                    trend = random.randint(0, 255)
                    shock = random.randint(0, 255)
                    risk = random.randint(0, 255)
                    meta32 = _pack_meta32(risk=risk, shock=shock, trend=trend, vitality=vitality)
                    titan_taxonomy32 = len(CLUSTER_CENTROIDS) & 0xFFFFFFFF
                    
                    all_assets.append({
                        "symbol": symbol,
                        "name": name,
                        "x": x,
                        "y": y,
                        "titan_taxonomy32": titan_taxonomy32,
                        "meta32": meta32,
                    })
            
            # Bulk insert in batches
            batch_size = 1000
            inserted = 0
            
            with engine.begin() as trans_conn:
                for i in range(0, len(all_assets), batch_size):
                    batch = all_assets[i:i + batch_size]
                    params = []
                    
                    for asset in batch:
                        params.append({
                            "symbol": asset["symbol"],
                            "name": asset["name"],
                            "x": asset["x"],
                            "y": asset["y"],
                            "titan_taxonomy32": asset["titan_taxonomy32"],
                            "meta32": asset["meta32"],
                            "is_active": True,
                        })
                    
                    trans_conn.execute(
                        text(
                            """
                            INSERT INTO assets 
                            (symbol, name, x, y, titan_taxonomy32, meta32, is_active)
                            VALUES 
                            (:symbol, :name, :x, :y, :titan_taxonomy32, :meta32, :is_active)
                            """
                        ),
                        params,
                    )
                    inserted += len(batch)
                    logger.debug(f"seed_titan_fallback: Inserted batch {i // batch_size + 1} ({len(batch)} assets)")
            
            logger.info(f"seed_titan_fallback: Successfully seeded {inserted} synthetic assets")
            return True
            
    except Exception as e:
        logger.error(f"seed_titan_fallback: Failed to seed: {e}", exc_info=True)
        return False
