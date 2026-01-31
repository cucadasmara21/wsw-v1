"""
Coordinate generation for assets (deterministic layout)
"""
import numpy as np
from typing import Tuple


def generate_coordinates(asset_id: int, category_id: int = 0, seed: int = 1337) -> Tuple[int, int]:
    """
    Generate deterministic (x, y) coordinates for an asset.
    Uses hash-based layout to create clustered "galaxy" structure.
    
    Args:
        asset_id: Asset ID
        category_id: Category ID (for clustering)
        seed: Random seed for reproducibility
    
    Returns:
        (x, y) tuple of uint16 coordinates (0-65535)
    """
    rng = np.random.RandomState(seed + asset_id)
    
    category_hash = hash(category_id) % 1000
    cluster_x = (category_hash % 32) * 2048
    cluster_y = ((category_hash // 32) % 32) * 2048
    
    jitter_x = rng.randint(0, 2048)
    jitter_y = rng.randint(0, 2048)
    
    x = (cluster_x + jitter_x) % 65536
    y = (cluster_y + jitter_y) % 65536
    
    return (int(x), int(y))
