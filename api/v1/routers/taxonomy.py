"""
Taxonomy API Router: Classification and bitmask endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import numpy as np

from database import get_db
from engines.taxonomy_engine import TaxonomyEngine
from engines.bitmask_encoder import unpack_taxonomy_mask

router = APIRouter(prefix="/api/v1/taxonomy", tags=["taxonomy"])


@router.get("/health")
async def taxonomy_health():
    """Health check for taxonomy engine"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "bitmask_layout": {
            "domain_bits": "0-2 (3 bits, 0-5)",
            "outlier_bit": "3 (1 bit, 0-1)",
            "risk_bits": "4-19 (16 bits, 0-65535)",
            "reserved_bits": "20-31 (12 bits)"
        }
    }


@router.post("/classify/{asset_id}")
async def classify_asset(
    asset_id: int,
    db: Session = Depends(get_db)
):
    """
    Classify a single asset and return its taxonomy bitmask.
    
    Returns:
        {
            "asset_id": int,
            "bitmask": int (32-bit),
            "components": {
                "domain": int (0-5),
                "outlier": int (0-1),
                "risk01": float (0.0-1.0)
            }
        }
    """
    try:
        engine = TaxonomyEngine(db)
        bitmask = engine.classify_asset(asset_id)
        
        # Unpack for human-readable response
        domain, outlier, risk01 = unpack_taxonomy_mask(bitmask)
        
        return {
            "asset_id": asset_id,
            "bitmask": int(bitmask),
            "bitmask_hex": f"0x{int(bitmask):08X}",
            "components": {
                "domain": domain,
                "outlier": outlier,
                "risk01": risk01,
                "risk_percent": round(risk01 * 100, 2)
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/classify-batch")
async def classify_batch(
    asset_ids: List[int],
    db: Session = Depends(get_db)
):
    """
    Classify multiple assets in batch.
    
    Request body:
        {
            "asset_ids": [1, 2, 3, ...]
        }
    
    Returns:
        {
            "bitmasks": [int, ...],  // 32-bit bitmasks
            "count": int
        }
    """
    try:
        if len(asset_ids) > 10000:
            raise HTTPException(status_code=400, detail="Batch size limited to 10,000 assets")
        
        engine = TaxonomyEngine(db)
        bitmasks = engine.classify_batch(asset_ids)
        
        return {
            "asset_ids": asset_ids,
            "bitmasks": [int(m) for m in bitmasks],
            "count": len(bitmasks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
