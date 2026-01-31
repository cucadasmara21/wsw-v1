"""
Morton-Z Spatial Hash Index: O(1) neighbor lookup via Z-order curve.

Converts (x, y) coordinates to 32-bit Morton codes using bit-interleaving.
Enables vectorized shock propagation with massive throughput.
Maintains 12-byte <HHII stride contract for exports.
"""
import numpy as np
from typing import Dict, List, Iterable, Optional
import logging

logger = logging.getLogger(__name__)


def morton_encode_32(x: int, y: int) -> int:
    """
    Encode (x, y) uint16 coordinates into 32-bit Morton code (Z-order curve).
    
    Bit-interleaving: x bits in even positions, y bits in odd positions.
    
    Args:
        x: X coordinate (0-65535)
        y: Y coordinate (0-65535)
    
    Returns:
        32-bit Morton code
    """
    x = int(x) & 0xFFFF
    y = int(y) & 0xFFFF
    
    # Spread bits: x -> even positions, y -> odd positions
    # Using magic numbers for bit-interleaving (16-bit each)
    x = (x | (x << 8)) & 0x00FF00FF
    x = (x | (x << 4)) & 0x0F0F0F0F
    x = (x | (x << 2)) & 0x33333333
    x = (x | (x << 1)) & 0x55555555
    
    y = (y | (y << 8)) & 0x00FF00FF
    y = (y | (y << 4)) & 0x0F0F0F0F
    y = (y | (y << 2)) & 0x33333333
    y = (y | (y << 1)) & 0x55555555
    
    # Interleave: x in even bits, y in odd bits
    morton = x | (y << 1)
    return morton & 0xFFFFFFFF


def morton_decode_32(morton: int) -> tuple[int, int]:
    """
    Decode 32-bit Morton code back to (x, y) coordinates.
    
    Args:
        morton: 32-bit Morton code
    
    Returns:
        (x, y) tuple of uint16 coordinates
    """
    morton = int(morton) & 0xFFFFFFFF
    
    # Extract x (even bits)
    x = morton & 0x55555555
    x = (x | (x >> 1)) & 0x33333333
    x = (x | (x >> 2)) & 0x0F0F0F0F
    x = (x | (x >> 4)) & 0x00FF00FF
    x = (x | (x >> 8)) & 0x0000FFFF
    
    # Extract y (odd bits)
    y = (morton >> 1) & 0x55555555
    y = (y | (y >> 1)) & 0x33333333
    y = (y | (y >> 2)) & 0x0F0F0F0F
    y = (y | (y >> 4)) & 0x00FF00FF
    y = (y | (y >> 8)) & 0x0000FFFF
    
    return (x, y)


def morton_encode_vectorized(x_coords: np.ndarray, y_coords: np.ndarray) -> np.ndarray:
    """
    Vectorized Morton encoding for NumPy arrays.
    
    Args:
        x_coords: Array of X coordinates (uint16)
        y_coords: Array of Y coordinates (uint16)
    
    Returns:
        Array of 32-bit Morton codes (uint32)
    """
    x = x_coords.astype(np.uint32) & 0xFFFF
    y = y_coords.astype(np.uint32) & 0xFFFF
    
    # Vectorized bit-interleaving
    x = (x | (x << 8)) & np.uint32(0x00FF00FF)
    x = (x | (x << 4)) & np.uint32(0x0F0F0F0F)
    x = (x | (x << 2)) & np.uint32(0x33333333)
    x = (x | (x << 1)) & np.uint32(0x55555555)
    
    y = (y | (y << 8)) & np.uint32(0x00FF00FF)
    y = (y | (y << 4)) & np.uint32(0x0F0F0F0F)
    y = (y | (y << 2)) & np.uint32(0x33333333)
    y = (y | (y << 1)) & np.uint32(0x55555555)
    
    morton = x | (y << 1)
    return morton.astype(np.uint32)


class PrefixBucketIndex:
    """
    Morton-Z Spatial Hash Index for O(1) neighbor lookup.
    
    Uses Z-order curve (Morton codes) to enable efficient spatial queries.
    Maintains 12-byte <HHII stride contract for exports.
    """
    
    def __init__(self, level_bits: int = 8):
        """
        Args:
            level_bits: Number of Morton code bits to use for bucket key (8-16 recommended).
                       Determines spatial resolution (2^level_bits buckets per dimension).
        """
        if not (4 <= level_bits <= 16):
            raise ValueError(f"level_bits must be 4-16, got {level_bits}")
        
        self.level_bits = level_bits
        self.bucket_mask = (0xFFFFFFFF >> (32 - level_bits * 2)) if level_bits * 2 <= 32 else 0xFFFFFFFF
        self.buckets: Dict[int, List[int]] = {}  # morton_prefix -> list of asset indices
        self.asset_indices: Optional[np.ndarray] = None
        self.morton_codes: Optional[np.ndarray] = None
        self.x_coords: Optional[np.ndarray] = None
        self.y_coords: Optional[np.ndarray] = None
    
    def build(self, x_coords: np.ndarray, y_coords: np.ndarray, asset_ids: Optional[np.ndarray] = None) -> 'PrefixBucketIndex':
        """
        Build index from coordinate arrays.
        
        Args:
            x_coords: X coordinates (uint16, shape: [n_assets])
            y_coords: Y coordinates (uint16, shape: [n_assets])
            asset_ids: Optional asset ID array (defaults to 0..n-1)
        
        Returns:
            self (for chaining)
        """
        n = len(x_coords)
        if n == 0:
            return self
        
        if len(y_coords) != n:
            raise ValueError(f"x_coords and y_coords must have same length, got {len(x_coords)} and {len(y_coords)}")
        
        self.x_coords = x_coords.astype(np.uint16)
        self.y_coords = y_coords.astype(np.uint16)
        
        # Compute Morton codes (vectorized)
        self.morton_codes = morton_encode_vectorized(self.x_coords, self.y_coords)
        
        # Build buckets using Morton prefix
        self.buckets.clear()
        
        if asset_ids is None:
            self.asset_indices = np.arange(n, dtype=np.int32)
        else:
            self.asset_indices = asset_ids.astype(np.int32)
        
        # Extract prefix from Morton codes
        prefixes = (self.morton_codes & self.bucket_mask) >> (32 - self.level_bits * 2)
        
        # Build buckets (vectorized grouping)
        for i in range(n):
            prefix = int(prefixes[i])
            if prefix not in self.buckets:
                self.buckets[prefix] = []
            self.buckets[prefix].append(i)
        
        logger.info(f"Morton-Z index built: {len(self.buckets)} buckets for {n} assets (level_bits={self.level_bits})")
        return self
    
    def query(self, morton_prefix: int) -> List[int]:
        """
        Query assets by Morton prefix.
        
        Args:
            morton_prefix: Morton code prefix (top level_bits*2 bits)
        
        Returns:
            List of asset indices matching prefix
        """
        normalized = (morton_prefix & self.bucket_mask) >> (32 - self.level_bits * 2)
        return self.buckets.get(normalized, []).copy()
    
    def neighbors(self, target_morton: int, radius: int = 1) -> Iterable[int]:
        """
        Get neighboring Morton codes within radius (spatial neighbors).
        
        Uses bit manipulation to find neighbors in Z-order space.
        
        Args:
            target_morton: Target Morton code
            radius: Spatial radius (in Morton space, not Euclidean)
        
        Yields:
            Asset indices from neighboring Morton buckets
        """
        target_prefix = (target_morton & self.bucket_mask) >> (32 - self.level_bits * 2)
        
        # Decode Morton prefix to approximate (x, y)
        x_approx, y_approx = morton_decode_32(target_morton)
        
        # Generate neighbor prefixes by perturbing coordinates
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                
                nx = max(0, min(65535, x_approx + dx * (1 << (16 - self.level_bits))))
                ny = max(0, min(65535, y_approx + dy * (1 << (16 - self.level_bits))))
                
                neighbor_morton = morton_encode_32(nx, ny)
                neighbor_prefix = (neighbor_morton & self.bucket_mask) >> (32 - self.level_bits * 2)
                
                if neighbor_prefix in self.buckets:
                    for idx in self.buckets[neighbor_prefix]:
                        yield idx
        
        # Also yield target prefix itself
        if target_prefix in self.buckets:
            for idx in self.buckets[target_prefix]:
                yield idx
    
    def apply_shock_vectorized(self, shock_intensities: np.ndarray, target_x: int, target_y: int, decay: float = 0.5) -> np.ndarray:
        """
        Vectorized shock application using Morton-Z spatial hash.
        
        Args:
            shock_intensities: Initial shock vector (n_assets,)
            target_x: Target X coordinate
            target_y: Target Y coordinate
            decay: Decay factor per spatial hop
        
        Returns:
            Updated shock vector (n_assets,)
        """
        if self.morton_codes is None:
            return shock_intensities.copy()
        
        target_morton = morton_encode_32(target_x, target_y)
        
        result = shock_intensities.copy()
        
        # Get all affected asset indices (vectorized)
        affected_indices = []
        affected_weights = []
        
        # Collect neighbors
        for idx in self.neighbors(target_morton, radius=1):
            affected_indices.append(idx)
            affected_weights.append(decay)
        
        # Direct hit (weight 1.0)
        target_prefix = (target_morton & self.bucket_mask) >> (32 - self.level_bits * 2)
        if target_prefix in self.buckets:
            for idx in self.buckets[target_prefix]:
                if idx not in affected_indices:
                    affected_indices.append(idx)
                    affected_weights.append(1.0)
        
        # Vectorized application
        if affected_indices:
            indices_array = np.array(affected_indices, dtype=np.int32)
            weights_array = np.array(affected_weights, dtype=np.float64)
            result[indices_array] += weights_array * shock_intensities[indices_array]
        
        return result
    
    def get_asset_count(self) -> int:
        """Get total number of indexed assets"""
        if self.asset_indices is None:
            return 0
        return len(self.asset_indices)
    
    def get_bucket_count(self) -> int:
        """Get number of Morton buckets"""
        return len(self.buckets)
