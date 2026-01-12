"""
Selection API - Dynamic Top-N Category Selection

Endpoints for previewing and recomputing category asset selection
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import User
from services.rbac_service import require_role, ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN
from services import selection_service, audit_service

router = APIRouter(tags=["selection"])


@router.get(
    "/categories/{category_id}/preview",
    summary="Preview category selection (non-persistent)"
)
async def preview_selection(
    category_id: int,
    top_n: int = Query(default=10, ge=1, le=50),
    lookback_days: int = Query(default=90, ge=7, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    Preview top-N asset selection for category without persisting results
    
    Calculates scores based on:
    - Volatility (20-day)
    - Max drawdown (90-day)
    - Momentum (30-day)
    - Liquidity (average volume)
    - Centrality (correlation with category average)
    - Data quality penalty (stale/confidence)
    
    Returns:
        {
            "selected": [{"asset_id", "symbol", "name", "score", "rank", "explain", "data_meta"}],
            "candidates": [...],
            "meta": {"category_id", "top_n", "lookback_days", "weights", "total_candidates"}
        }
    """
    try:
        result = selection_service.preview_category_selection(
            db=db,
            category_id=category_id,
            top_n=top_n,
            lookback_days=lookback_days
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Selection preview failed: {str(e)}")


@router.post(
    "/categories/{category_id}/recompute",
    summary="Recompute and persist category selection"
)
async def recompute_selection(
    category_id: int,
    top_n: int = Query(default=10, ge=1, le=50),
    lookback_days: int = Query(default=90, ge=7, le=365),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    Recompute selection and persist results
    
    Updates:
    - CategoryAsset.is_selected flags
    - CategoryAsset.score_ema (with stability smoothing)
    - CategoryAsset.last_score, last_rank
    - Creates SelectionRun record
    
    Uses EMA smoothing (alpha=0.3) and hysteresis to avoid churn.
    
    Returns same structure as preview endpoint.
    """
    try:
        result = selection_service.recompute_category_selection(
            db=db,
            category_id=category_id,
            top_n=top_n,
            lookback_days=lookback_days,
            persist=True
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result)
        
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Selection recompute failed: {str(e)}")
    finally:
        try:
            audit_service.log_action(
                action="recompute_selection",
                entity_type="category",
                entity_id=category_id,
                metadata={"top_n": top_n, "lookback_days": lookback_days},
                db=db,
                user=user,
            )
        except Exception:
            pass


@router.get(
    "/categories/{category_id}/current",
    summary="Get current persisted selection"
)
async def get_current_selection(
    category_id: int,
    top_n: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    Get currently selected assets based on persisted flags
    
    Returns assets with is_selected=True from CategoryAsset table.
    Does not recalculate scores.
    
    Returns:
        {
            "selected": [{"asset_id", "symbol", "name", "score", "rank", "score_ema", "last_selected_at"}],
            "meta": {"category_id", "category_name", "source": "persisted_flags"}
        }
    """
    try:
        result = selection_service.get_current_selection(
            db=db,
            category_id=category_id,
            top_n=top_n
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get current selection: {str(e)}")
