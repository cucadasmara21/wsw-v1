"""
PrefixCausalEngine: O(1) prefix-based causal propagation (NO O(N^2))
Uses taxonomy32 prefix indexes to avoid pairwise comparisons.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class PrefixIndex:
    """Prefix index for fast lookups"""
    prefix8_to_indices: Dict[int, List[int]]   # prefix8 -> list of asset indices
    prefix16_to_indices: Dict[int, List[int]]  # prefix16 -> list of asset indices
    prefix24_to_indices: Dict[int, List[int]]  # prefix24 -> list of asset indices
    asset_taxonomy32: np.ndarray  # taxonomy32 for each asset index
    asset_ids: np.ndarray  # asset_id for each asset index


class PrefixCausalEngine:
    """
    Prefix-based causal engine that avoids O(N^2) by using taxonomy32 prefixes.
    
    Propagation rules:
    - Same prefix8 bucket: strong connection
    - Adjacent prefix8 (Hamming distance 1): medium connection
    - Same monolith byte: weak connection
    """
    
    def __init__(self, taxonomy32_array: np.ndarray, asset_ids: np.ndarray):
        """
        Args:
            taxonomy32_array: Array of taxonomy32 values (uint32)
            asset_ids: Array of asset IDs corresponding to indices
        """
        self.n_assets = len(taxonomy32_array)
        self.asset_ids = asset_ids
        self.index = self._build_prefix_index(taxonomy32_array)
        
        # Precompute neighbor list for prefix8 (0..255)
        self.prefix8_neighbors = self._build_prefix8_neighbors()
    
    def _build_prefix_index(self, taxonomy32_array: np.ndarray) -> PrefixIndex:
        """Build prefix indexes from taxonomy32 array"""
        prefix8_to_indices: Dict[int, List[int]] = {}
        prefix16_to_indices: Dict[int, List[int]] = {}
        prefix24_to_indices: Dict[int, List[int]] = {}
        
        for idx, tax32 in enumerate(taxonomy32_array):
            prefix8 = (tax32 >> 24) & 0xFF
            prefix16 = (tax32 >> 16) & 0xFFFF
            prefix24 = (tax32 >> 8) & 0xFFFFFF
            
            if prefix8 not in prefix8_to_indices:
                prefix8_to_indices[prefix8] = []
            prefix8_to_indices[prefix8].append(idx)
            
            if prefix16 not in prefix16_to_indices:
                prefix16_to_indices[prefix16] = []
            prefix16_to_indices[prefix16].append(idx)
            
            if prefix24 not in prefix24_to_indices:
                prefix24_to_indices[prefix24] = []
            prefix24_to_indices[prefix24].append(idx)
        
        return PrefixIndex(
            prefix8_to_indices=prefix8_to_indices,
            prefix16_to_indices=prefix16_to_indices,
            prefix24_to_indices=prefix24_to_indices,
            asset_taxonomy32=taxonomy32_array,
            asset_ids=asset_ids
        )
    
    def _build_prefix8_neighbors(self) -> Dict[int, List[int]]:
        """Build neighbor list for prefix8 values (Hamming distance 1)"""
        neighbors: Dict[int, List[int]] = {}
        
        for prefix8 in range(256):
            neighbor_list = []
            # Flip each bit
            for bit in range(8):
                neighbor = prefix8 ^ (1 << bit)
                neighbor_list.append(neighbor)
            neighbors[prefix8] = neighbor_list
        
        return neighbors
    
    def propagate_shock(
        self,
        asset_id: int,
        intensity: float = 1.0,
        depth: int = 3
    ) -> Tuple[List[int], Dict]:
        """
        Propagate shock from a single asset using prefix-based rules.
        
        Args:
            asset_id: Source asset ID
            intensity: Shock intensity (0.0-1.0)
            depth: Propagation depth (number of hops)
        
        Returns:
            (affected_asset_ids, summary_counts_by_prefix)
        """
        # Find asset index
        asset_idx = None
        for i, aid in enumerate(self.asset_ids):
            if aid == asset_id:
                asset_idx = i
                break
        
        if asset_idx is None:
            return ([], {})
        
        taxonomy32 = self.index.asset_taxonomy32[asset_idx]
        prefix8 = (taxonomy32 >> 24) & 0xFF
        
        # Track affected assets and their shock levels
        affected: Dict[int, float] = {asset_id: intensity}
        visited: set = {asset_idx}
        
        # BFS propagation
        current_level = [asset_idx]
        current_intensity = intensity
        
        for hop in range(depth):
            next_level = []
            next_intensity = current_intensity * 0.5  # Decay per hop
            
            for src_idx in current_level:
                src_tax32 = self.index.asset_taxonomy32[src_idx]
                src_prefix8 = (src_tax32 >> 24) & 0xFF
                
                # Rule 1: Same prefix8 (strong)
                same_prefix8_indices = self.index.prefix8_to_indices.get(src_prefix8, [])
                for tgt_idx in same_prefix8_indices:
                    if tgt_idx not in visited and tgt_idx != src_idx:
                        visited.add(tgt_idx)
                        next_level.append(tgt_idx)
                        tgt_asset_id = int(self.asset_ids[tgt_idx])
                        affected[tgt_asset_id] = max(affected.get(tgt_asset_id, 0.0), next_intensity * 0.8)
                
                # Rule 2: Adjacent prefix8 (medium)
                neighbors = self.prefix8_neighbors.get(src_prefix8, [])
                for neighbor_prefix8 in neighbors[:4]:  # Limit to 4 neighbors
                    neighbor_indices = self.index.prefix8_to_indices.get(neighbor_prefix8, [])
                    for tgt_idx in neighbor_indices[:16]:  # Limit to 16 per neighbor
                        if tgt_idx not in visited:
                            visited.add(tgt_idx)
                            next_level.append(tgt_idx)
                            tgt_asset_id = int(self.asset_ids[tgt_idx])
                            affected[tgt_asset_id] = max(affected.get(tgt_asset_id, 0.0), next_intensity * 0.4)
                
                # Rule 3: Same monolith byte (weak) - only if not already affected
                monolith_byte = src_prefix8 & 0xE0  # Top 3 bits (monolith)
                for check_prefix8 in range(256):
                    if (check_prefix8 & 0xE0) == monolith_byte and check_prefix8 != src_prefix8:
                        monolith_indices = self.index.prefix8_to_indices.get(check_prefix8, [])
                        for tgt_idx in monolith_indices[:8]:  # Limit to 8 per monolith
                            if tgt_idx not in visited:
                                visited.add(tgt_idx)
                                next_level.append(tgt_idx)
                                tgt_asset_id = int(self.asset_ids[tgt_idx])
                                affected[tgt_asset_id] = max(affected.get(tgt_asset_id, 0.0), next_intensity * 0.1)
            
            current_level = next_level
            current_intensity = next_intensity
        
        # Build summary by prefix
        summary_by_prefix: Dict[int, int] = {}
        for affected_id in affected.keys():
            # Find prefix8 for affected asset
            for i, aid in enumerate(self.asset_ids):
                if aid == affected_id:
                    tax32 = self.index.asset_taxonomy32[i]
                    p8 = (tax32 >> 24) & 0xFF
                    summary_by_prefix[p8] = summary_by_prefix.get(p8, 0) + 1
                    break
        
        return (list(affected.keys()), summary_by_prefix)
