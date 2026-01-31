"""
CausalMux: Top-K sparse causal graph + Bayesian shock propagation
Implements vectorized, sparse, deterministic causal inference.

Key constraints:
- Never allocate dense NxN matrices for N > 5000
- Top-K by construction (K=32..256)
- SpMV only (no O(N^3))
- Deterministic outputs (same snapshot+seed → same results)
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Optional dependencies (graceful degradation)
try:
    from scipy import sparse
    from scipy.sparse import csr_matrix
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("scipy not available; using pure NumPy (slower)")

try:
    from numba import njit, prange
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    logger.warning("numba not available; using pure NumPy (slower)")


@dataclass
class CausalEdge:
    """Single edge in causal graph"""
    source: int      # Asset ID index
    target: int      # Asset ID index
    strength: float  # Edge weight (0.0-1.0)
    lag: int         # Lag in timesteps
    confidence: float  # Confidence score (0.0-1.0)
    method_version: str  # Method used to compute edge


@dataclass
class CausalGraph:
    """Sparse causal graph representation"""
    n_assets: int
    edges: List[CausalEdge]
    asset_ids: np.ndarray  # Mapping: index → asset_id
    
    def to_csr(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Convert to CSR (Compressed Sparse Row) format for SpMV.
        
        Returns:
            (indices, indptr, data) for scipy.sparse.csr_matrix
        """
        # Build adjacency list
        adj_list: Dict[int, List[Tuple[int, float]]] = {i: [] for i in range(self.n_assets)}
        
        for edge in self.edges:
            adj_list[edge.source].append((edge.target, edge.strength))
        
        # Convert to CSR format
        indices = []
        indptr = [0]
        data = []
        
        for i in range(self.n_assets):
            neighbors = adj_list[i]
            for target, strength in neighbors:
                indices.append(target)
                data.append(strength)
            indptr.append(len(indices))
        
        return (np.array(indices, dtype=np.int32), 
                np.array(indptr, dtype=np.int32),
                np.array(data, dtype=np.float64))


class CausalGraphBuilder:
    """
    Builds Top-K sparse causal graph from returns data.
    Never allocates dense NxN matrices.
    """
    
    def __init__(self, top_k: int = 64, window: int = 90, min_confidence: float = 0.3):
        """
        Args:
            top_k: Maximum neighbors per node (default 64)
            window: Rolling window size in days (default 90)
            min_confidence: Minimum confidence threshold (default 0.3)
        """
        self.top_k = top_k
        self.window = window
        self.min_confidence = min_confidence
    
    def build_graph(
        self,
        returns: np.ndarray,  # Shape: (n_assets, n_timesteps)
        asset_ids: np.ndarray,  # Shape: (n_assets,)
        method: str = "correlation"
    ) -> CausalGraph:
        """
        Build Top-K sparse causal graph.
        
        Args:
            returns: Asset returns matrix (n_assets × n_timesteps)
            asset_ids: Asset ID array (n_assets,)
            method: "correlation" or "lead_lag"
        
        Returns:
            CausalGraph with Top-K edges per node
        """
        n_assets, n_timesteps = returns.shape
        
        if n_assets > 5000:
            logger.warning(f"Large graph (N={n_assets}); using Top-K={self.top_k} to avoid O(N^2)")
        
        edges: List[CausalEdge] = []
        
        # Process in chunks to avoid memory explosion
        chunk_size = 1000
        for i_start in range(0, n_assets, chunk_size):
            i_end = min(i_start + chunk_size, n_assets)
            chunk_returns = returns[i_start:i_end, :]
            
            # Compute correlations/lead-lag for this chunk
            for i in range(i_end - i_start):
                source_idx = i_start + i
                source_returns = chunk_returns[i, :]
                
                # Compute scores with all other assets (but only keep Top-K)
                # PROHIBITED: O(N^2) for N >= 10k
                if n_assets >= 10000:
                    logger.warning(f"N={n_assets} >= 10k: Skipping O(N^2) correlation. Use prefix engine instead.")
                    # Return empty edges for this chunk to force prefix engine usage
                    continue
                
                scores: List[Tuple[int, float]] = []
                
                for j in range(n_assets):
                    if i == j:
                        continue
                    
                    target_returns = returns[j, :]
                    
                    if method == "correlation":
                        score = self._compute_correlation(source_returns, target_returns)
                    elif method == "lead_lag":
                        score = self._compute_lead_lag(source_returns, target_returns)
                    else:
                        score = 0.0
                    
                    if abs(score) >= self.min_confidence:
                        scores.append((j, abs(score)))
                
                # Keep only Top-K
                scores.sort(key=lambda x: x[1], reverse=True)
                top_scores = scores[:self.top_k]
                
                # Create edges
                for target_idx, strength in top_scores:
                    edges.append(CausalEdge(
                        source=source_idx,
                        target=target_idx,
                        strength=strength,
                        lag=0,  # Simplified (could compute actual lag)
                        confidence=strength,
                        method_version=method
                    ))
        
        return CausalGraph(
            n_assets=n_assets,
            edges=edges,
            asset_ids=asset_ids
        )
    
    def _compute_correlation(self, x: np.ndarray, y: np.ndarray) -> float:
        """Compute Pearson correlation"""
        if len(x) < 2 or len(y) < 2:
            return 0.0
        
        x_centered = x - np.mean(x)
        y_centered = y - np.mean(y)
        
        numerator = np.dot(x_centered, y_centered)
        raw_denom = np.sqrt(np.dot(x_centered, x_centered) * np.dot(y_centered, y_centered))
        # P-02: branchless kappa clamp (no div by zero)
        denominator = max(float(raw_denom), 1e-3)
        return numerator / denominator
    
    def _compute_lead_lag(self, x: np.ndarray, y: np.ndarray, max_lag: int = 5) -> float:
        """Compute lead-lag correlation (simplified)"""
        best_score = 0.0
        
        for lag in range(-max_lag, max_lag + 1):
            if lag == 0:
                score = self._compute_correlation(x, y)
            elif lag > 0:
                # x leads y
                if len(x) > lag:
                    score = self._compute_correlation(x[:-lag], y[lag:])
                else:
                    score = 0.0
            else:
                # y leads x
                if len(y) > abs(lag):
                    score = self._compute_correlation(x[abs(lag):], y[:-abs(lag)])
                else:
                    score = 0.0
            
            best_score = max(best_score, abs(score))
        
        return best_score


class BayesianPropagationEngine:
    """
    Bayesian shock propagation using sparse matrix-vector multiplication (SpMV).
    Implements: s_{k+1} = γ * W^T * s_k
    """
    
    def __init__(self, graph: CausalGraph, decay_factor: float = 0.15, max_iter: int = 10, eps: float = 1e-6):
        """
        Args:
            graph: CausalGraph (sparse)
            decay_factor: Propagation decay (γ, default 0.15)
            max_iter: Maximum iterations (default 10)
            eps: Convergence threshold (default 1e-6)
        """
        self.graph = graph
        self.decay_factor = decay_factor
        self.max_iter = max_iter
        self.eps = eps
        
        # Build CSR matrix for SpMV
        if SCIPY_AVAILABLE:
            indices, indptr, data = graph.to_csr()
            self.W = csr_matrix((data, indices, indptr), shape=(graph.n_assets, graph.n_assets))
        else:
            # Fallback: build dense matrix (only if N < 5000)
            if graph.n_assets > 5000:
                raise ValueError("Graph too large for dense matrix; install scipy for sparse support")
            self.W = self._build_dense_matrix(graph)
    
    def propagate_shock(
        self,
        shock_vector: np.ndarray,  # Initial shock (n_assets,)
        domain_mask: Optional[np.ndarray] = None  # Optional domain filter
    ) -> Tuple[np.ndarray, Dict]:
        """
        Propagate shock through causal graph.
        
        Args:
            shock_vector: Initial shock intensities (n_assets,)
            domain_mask: Optional boolean mask to filter assets by domain
        
        Returns:
            (propagated_shock, diagnostics)
        """
        if len(shock_vector) != self.graph.n_assets:
            raise ValueError(f"Shock vector length {len(shock_vector)} != graph size {self.graph.n_assets}")
        
        # Apply domain mask if provided
        if domain_mask is not None:
            shock_vector = shock_vector * domain_mask.astype(np.float64)
        
        s_k = shock_vector.copy()
        diagnostics = {
            "iterations": 0,
            "converged": False,
            "final_norm": 0.0
        }
        
        # Iterative propagation: s_{k+1} = γ * W^T * s_k
        for iteration in range(self.max_iter):
            if SCIPY_AVAILABLE:
                # SpMV: s_{k+1} = γ * W^T * s_k
                s_k_next = self.decay_factor * self.W.T.dot(s_k)
            else:
                # Dense fallback
                s_k_next = self.decay_factor * (self.W.T @ s_k)
            
            # Check convergence
            diff_norm = np.linalg.norm(s_k_next - s_k)
            diagnostics["final_norm"] = float(diff_norm)
            
            if diff_norm < self.eps:
                diagnostics["converged"] = True
                diagnostics["iterations"] = iteration + 1
                break
            
            s_k = s_k_next
            diagnostics["iterations"] = iteration + 1
        
        # Normalize to preserve total energy (P-02: kappa clamp, E clamp [-8,8])
        KAPPA_MIN = 1e-3
        max_shock = float(np.max(np.abs(s_k)))
        denom = max(max_shock, KAPPA_MIN)
        s_k = s_k / denom
        s_k = np.clip(s_k, 0.0, 8.0)  # P-02: energy E clamp [0, 8]
        
        return s_k, diagnostics
    
    def _build_dense_matrix(self, graph: CausalGraph) -> np.ndarray:
        """Build dense adjacency matrix (fallback, only for small graphs)"""
        W = np.zeros((graph.n_assets, graph.n_assets), dtype=np.float64)
        for edge in graph.edges:
            W[edge.source, edge.target] = edge.strength
        return W
    
    def propagate_shock_prefix(
        self,
        shock_vector: np.ndarray,
        prefix_index,  # PrefixBucketIndex instance
        target_prefix: int,
        decay: float = 0.5
    ) -> Tuple[np.ndarray, Dict]:
        """
        Fast-path shock propagation using PrefixBucketIndex (for N >= 10k).
        
        Args:
            shock_vector: Initial shock intensities (n_assets,)
            prefix_index: PrefixBucketIndex instance
            target_prefix: Prefix to shock
            decay: Decay factor per hop (default 0.5)
        
        Returns:
            (propagated_shock, diagnostics)
        """
        import time
        start_ms = time.time() * 1000
        
        # Use vectorized prefix bucket shock application
        result = prefix_index.apply_shock_vectorized(shock_vector, target_prefix, decay)
        
        # Count affected assets
        affected_count = np.count_nonzero(result > shock_vector)
        
        elapsed_ms = time.time() * 1000 - start_ms
        
        diagnostics = {
            "method": "prefix_bucket",
            "avg_ms": elapsed_ms,
            "affected_count": int(affected_count),
            "prefix_len": prefix_index.prefix_bits,
            "target_prefix": target_prefix
        }
        
        return result, diagnostics
