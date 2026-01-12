from __future__ import annotations

"""
Metrics API endpoints
RBAC-protected
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, User, AssetMetricSnapshot
from schemas import MetricsSnapshot, MetricSnapshotOut, LeaderboardItem
from services.rbac_service import require_role, has_role_or_higher, ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN
from services.metrics_registry import registry
from services.alerts_service import AlertsService
from services.metrics_engine import compute_metrics_for_asset, save_snapshot, latest_snapshot, leaderboard
from services import audit_service

router = APIRouter(tags=["metrics"])


@router.get("/{asset_id}/metrics", response_model=MetricsSnapshot, summary="Get latest metrics snapshot")
async def get_asset_metrics(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    """Get latest metrics snapshot for an asset"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Get latest snapshot
    snapshot = (
        db.query(AssetMetricSnapshot)
        .filter(AssetMetricSnapshot.asset_id == asset_id)
        .order_by(AssetMetricSnapshot.as_of.desc())
        .first()
    )
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="No metrics snapshot found for this asset")
    
    return snapshot


@router.post("/{asset_id}/metrics/recompute", response_model=MetricsSnapshot, summary="Recompute metrics")
async def recompute_asset_metrics(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    Recompute metrics for an asset.
    Requires analyst or admin role.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # TODO: Fetch bars from database (Price model)
    # For now, create empty snapshot as placeholder
    bars = []  # Would fetch from db.query(Price).filter(...).all()
    
    # Compute metrics using registry
    result = registry.compute(asset, bars, asset.category_id)
    
    # Save snapshot
    snapshot = AssetMetricSnapshot(
        asset_id=asset_id,
        as_of=asset.created_at,  # Placeholder: should be market timestamp
        metrics=result["metrics"],
        quality=result["quality"],
        explain=result["explain"]
    )
    db.add(snapshot)
    
    # Generate alerts
    AlertsService.generate_alerts(asset, result["metrics"], result["quality"], db)
    
    db.commit()
    db.refresh(snapshot)
    
    return snapshot


@router.get("/{asset_id}/latest", response_model=MetricSnapshotOut, summary="Get latest metric snapshot (scored)")
async def get_latest_metric_snapshot(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    snap = latest_snapshot(db, asset_id)
    if not snap:
        raise HTTPException(status_code=404, detail="No metric snapshot found")
    return snap


@router.post("/{asset_id}/recompute", response_model=MetricSnapshotOut, summary="Recompute metrics and score")
async def recompute_metric_snapshot(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ANALYST, ROLE_ADMIN]))
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    result = compute_metrics_for_asset(db, asset)
    snap = save_snapshot(db, asset_id, result)
    try:
        audit_service.log_action(
            action="recompute_metrics",
            entity_type="asset",
            entity_id=asset_id,
            metadata={},
            db=db,
            user=user,
        )
    except Exception:
        pass
    return snap


@router.get("/leaderboard", response_model=List[LeaderboardItem], summary="Top assets by risk score")
async def metrics_leaderboard(
    category_id: int | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    items = leaderboard(db, category_id=category_id, limit=limit)
    return items
