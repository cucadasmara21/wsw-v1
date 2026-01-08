"""
Endpoints para métricas de riesgo
SQLAlchemy 2.x compatible
"""
from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Asset, RiskMetric
from schemas import RiskOverviewResponse

router = APIRouter()


@router.get("/overview", response_model=List[RiskOverviewResponse])
async def get_risk_overview(
    limit: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """Obtener visión general de riesgo para todos los activos"""
    try:
        assets = db.query(Asset).filter(Asset.is_active == True).limit(limit).all()

        results = []
        for asset in assets:
            # Obtener último CRI para este activo
            latest_metric = db.query(RiskMetric).filter(
                RiskMetric.asset_id == asset.id,
                RiskMetric.metric_name == "cri"
            ).order_by(RiskMetric.time.desc()).first()

            cri = latest_metric.metric_value if latest_metric else 0.0

            if cri >= 80:
                risk_level = "critical"
            elif cri >= 60:
                risk_level = "high"
            elif cri >= 40:
                risk_level = "medium"
            elif cri >= 20:
                risk_level = "low"
            else:
                risk_level = "very_low"

            results.append({
                "asset_id": asset.id,
                "symbol": asset.symbol,
                "current_price": None,
                "cri": cri,
                "risk_level": risk_level,
                "last_updated": latest_metric.time if latest_metric else datetime.utcnow()
            })

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/asset/{asset_id}")
async def get_asset_risk(
    asset_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """Obtener métricas de riesgo para un activo específico"""
    try:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")

        start_date = datetime.utcnow() - timedelta(days=days)
        metrics = db.query(RiskMetric).filter(
            RiskMetric.asset_id == asset_id,
            RiskMetric.time >= start_date
        ).order_by(RiskMetric.time).all()

        return {
            "asset":  asset.to_dict(),
            "metrics": [
                {
                    "time": m.time,
                    "metric_name": m.metric_name,
                    "metric_value": m.metric_value
                }
                for m in metrics
            ],
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))