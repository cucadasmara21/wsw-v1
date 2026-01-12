from __future__ import annotations

"""
Alerts API endpoints
RBAC-protected
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, User, Alert
from schemas import AlertOut
from services.rbac_service import require_role, ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN
from services.alerts_service import AlertsService

router = APIRouter(tags=["alerts"])


@router.get("", response_model=List[AlertOut], summary="List alerts")
async def list_alerts(
    asset_id: Optional[int] = Query(None),
    severity: Optional[str] = Query(None),
    active: bool = Query(True),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    List alerts with optional filters.
    
    - **asset_id**: Filter by specific asset
    - **severity**: Filter by severity (info, warning, critical)
    - **active**: If True, only unresolved alerts
    """
    query = db.query(Alert)
    
    if asset_id:
        query = query.filter(Alert.asset_id == asset_id)
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    if active:
        query = query.filter(Alert.resolved_at == None)
    
    alerts = query.order_by(Alert.triggered_at.desc()).offset(skip).limit(limit).all()
    return alerts


@router.post("/{alert_id}/resolve", response_model=AlertOut, summary="Resolve alert")
async def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ANALYST, ROLE_ADMIN]))
):
    """Mark an alert as resolved"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    AlertsService.resolve_alert(alert_id, db)
    db.refresh(alert)
    return alert


@router.post("/recompute", summary="Recompute all alerts")
async def recompute_all_alerts(
    asset_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    Recompute alerts for all assets or a specific asset.
    This is a long-running operation that would typically be done async.
    """
    # TODO: Implement async task queue for this
    return {"status": "queued", "message": "Alert recomputation queued"}
