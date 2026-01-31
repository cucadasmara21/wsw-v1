"""
Causal Simulation API Router
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import numpy as np
from datetime import datetime
import time

from database import get_db
from models import Asset, Price
from engines.causal_mux import CausalGraphBuilder, BayesianPropagationEngine
from engines.taxonomy_engine import TaxonomyEngine
from engines.prefix_causal import PrefixCausalEngine
from sqlalchemy import text
import numpy as np

router = APIRouter(prefix="/api/v1/causal", tags=["causal"])


@router.post("/simulate")
async def simulate_scenario(
    asset_ids: List[int],
    shock_domain: Optional[int] = None,  # Domain to shock (0-5)
    shock_intensity: float = 0.3,
    top_k: int = 64,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    Run causal simulation with shock propagation.
    
    Args:
        asset_ids: List of asset IDs to simulate
        shock_domain: Domain to shock (0-5, None = shock all)
        shock_intensity: Initial shock magnitude (0.0-1.0)
        top_k: Top-K neighbors per node (default 64)
    
    Returns:
        {
            "simulation_id": str,
            "propagated_shocks": List[float],
            "diagnostics": dict,
            "latency_ms": float
        }
    """
    start_time = time.perf_counter()
    
    try:
        if len(asset_ids) > 10000:
            raise HTTPException(status_code=400, detail="Simulation limited to 10,000 assets")
        
        # Load asset returns (simplified: use latest prices)
        # In production, this would load historical returns from Price table
        n_assets = len(asset_ids)
        
        # Mock returns data (in production, load from Price table)
        # For MVP, generate synthetic returns
        n_timesteps = 90  # 90-day window
        returns = np.random.randn(n_assets, n_timesteps) * 0.02  # 2% daily volatility
        
        # Build causal graph
        graph_builder = CausalGraphBuilder(top_k=top_k, window=90)
        asset_ids_array = np.array(asset_ids)
        graph = graph_builder.build_graph(returns, asset_ids_array, method="correlation")
        
        # Create propagation engine
        prop_engine = BayesianPropagationEngine(graph, decay_factor=0.15, max_iter=10)
        
        # Create initial shock vector
        shock_vector = np.zeros(n_assets, dtype=np.float64)
        
        if shock_domain is not None:
            # Shock assets in specific domain
            taxonomy_engine = TaxonomyEngine(db)
            bitmasks = taxonomy_engine.classify_batch(asset_ids)
            
            for i, mask in enumerate(bitmasks):
                domain = int(mask & 0x7)
                if domain == shock_domain:
                    shock_vector[i] = shock_intensity
        else:
            # Shock all assets uniformly
            shock_vector[:] = shock_intensity
        
        # Propagate shock
        propagated, diagnostics = prop_engine.propagate_shock(shock_vector)
        
        # Measure latency
        latency_ms = (time.perf_counter() - start_time) * 1000
        
        # Check performance budget
        if latency_ms > 200:
            diagnostics["degraded_mode"] = True
            diagnostics["reason"] = f"Latency {latency_ms:.1f}ms exceeds 200ms threshold"
        
        return {
            "simulation_id": f"sim_{int(time.time())}",
            "asset_ids": asset_ids,
            "propagated_shocks": propagated.tolist(),
            "diagnostics": {
                **diagnostics,
                "n_assets": n_assets,
                "n_edges": len(graph.edges),
                "sparsity": 1.0 - (len(graph.edges) / (n_assets * n_assets)) if n_assets > 0 else 0.0
            },
            "latency_ms": round(latency_ms, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/propagate")
async def propagate_shock_prefix(
    asset_id: int,
    intensity: float = 1.0,
    depth: int = 3,
    limit: int = 100000,
    db: Session = Depends(get_db)
):
    """
    Propagate shock using prefix-based engine (NO O(N^2)).
    
    Args:
        asset_id: Source asset ID
        intensity: Shock intensity (0.0-1.0)
        depth: Propagation depth (number of hops, default 3)
        limit: Maximum assets to load (default 100000)
    
    Returns:
        {
            "affected_asset_ids": List[int],
            "summary_by_prefix": Dict[int, int],
            "n_affected": int
        }
    """
    try:
        # Load taxonomy32 and asset_ids from database
        result = db.execute(text("""
            SELECT id, COALESCE(taxonomy32, 0) as taxonomy32
            FROM assets
            WHERE is_active = 1
            LIMIT :limit
        """), {"limit": limit})
        
        rows = result.fetchall()
        
        if not rows:
            return {
                "affected_asset_ids": [],
                "summary_by_prefix": {},
                "n_affected": 0
            }
        
        asset_ids = np.array([int(r[0]) for r in rows], dtype=np.int32)
        taxonomy32_array = np.array([int(r[1] or 0) for r in rows], dtype=np.uint32)
        
        # Create prefix engine
        engine = PrefixCausalEngine(taxonomy32_array, asset_ids)
        
        # Propagate shock
        affected_ids, summary_by_prefix = engine.propagate_shock(
            asset_id=asset_id,
            intensity=intensity,
            depth=depth
        )
        
        return {
            "affected_asset_ids": affected_ids,
            "summary_by_prefix": {str(k): v for k, v in summary_by_prefix.items()},
            "n_affected": len(affected_ids)
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
