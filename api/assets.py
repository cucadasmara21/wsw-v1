from __future__ import annotations

"""
Endpoints para gestión de activos
SQLAlchemy 2.x compatible
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import Asset, Price
from schemas import Asset as AssetSchema, AssetCreate, AssetUpdate

router = APIRouter()


@router.get("/", response_model=List[AssetSchema])
async def get_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(True),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Obtener lista de activos"""
    try:
        query = db.query(Asset)
        if active_only:
            query = query.filter(Asset.is_active == True)
        if category:
            query = query.filter(Asset.category == category)

        assets = query.order_by(Asset.symbol).offset(skip).limit(limit).all()
        return assets
    except Exception as e: 
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{asset_id}", response_model=AssetSchema)
async def get_asset(asset_id: int, db: Session = Depends(get_db)):
    """Obtener un activo por ID"""
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("/", response_model=AssetSchema, status_code=201)
async def create_asset(asset_data: AssetCreate, db: Session = Depends(get_db)):
    """Crear un nuevo activo"""
    existing = db.query(Asset).filter(Asset.symbol == asset_data.symbol).first()
    if existing:
        raise HTTPException(status_code=400, detail="Asset with this symbol already exists")

    db_asset = Asset(**asset_data.dict())
    db.add(db_asset)
    db.commit()
    db.refresh(db_asset)
    return db_asset


@router.get("/summary/stats")
async def get_assets_summary(db: Session = Depends(get_db)):
    """Obtener resumen estadístico de activos"""
    try:
        total_assets = db.query(func.count(Asset.id)).filter(Asset.is_active == True).scalar()

        return {
            "total_assets":  total_assets,
            "active_assets": total_assets,
            "total_prices": db.query(func.count(Price.time)).scalar() or 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # api/assets.py

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, select, or_

from database import get_db
from models import Asset, RiskSnapshot
from schemas import PagedAssetsOut, AssetOut, AssetDetailOut, RiskSnapshotOut

# use module-level `router` (registered in main.py with prefix `/api/assets`)
router = APIRouter(tags=["assets"])


@router.get("", response_model=PagedAssetsOut)
def list_assets(
    q: str | None = Query(None, description="Search by symbol or name"),
    category_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    base = select(Asset)
    if category_id is not None:
        base = base.where(Asset.category_id == category_id)

    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Asset.symbol.ilike(like), Asset.name.ilike(like)))

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    items = db.execute(base.order_by(Asset.id).limit(limit).offset(offset)).scalars().all()

    return PagedAssetsOut(
        total=int(total),
        items=[AssetOut(id=a.id, symbol=a.symbol, name=a.name, asset_type=a.asset_type, category_id=a.category_id) for a in items],
    )


@router.get("/{asset_id}", response_model=AssetDetailOut)
def asset_detail(asset_id: int, db: Session = Depends(get_db)):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found")

    latest = db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.asset_id == asset_id)
        .order_by(RiskSnapshot.ts.desc())
        .limit(1)
    ).scalars().first()

    latest_out = None
    if latest:
        latest_out = RiskSnapshotOut(
            ts=latest.ts,
            price_risk=latest.price_risk,
            liq_risk=latest.liq_risk,
            fund_risk=latest.fund_risk,
            cp_risk=latest.cp_risk,
            regime_risk=latest.regime_risk,
            cri=latest.cri,
            model_version=latest.model_version,
        )

    return AssetDetailOut(
        id=a.id,
        symbol=a.symbol,
        name=a.name,
        asset_type=a.asset_type,
        category_id=a.category_id,
        latest=latest_out,
    )


@router.get("/{asset_id}/risk_history", response_model=list[RiskSnapshotOut])
def asset_risk_history(
    asset_id: int,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(status_code=404, detail="Asset not found")

    rows = db.execute(
        select(RiskSnapshot)
        .where(RiskSnapshot.asset_id == asset_id)
        .order_by(RiskSnapshot.ts.desc())
        .limit(limit)
    ).scalars().all()

    # lo devolvemos en orden cronológico para gráficos
    rows = list(reversed(rows))

    return [
        RiskSnapshotOut(
            ts=r.ts,
            price_risk=r.price_risk,
            liq_risk=r.liq_risk,
            fund_risk=r.fund_risk,
            cp_risk=r.cp_risk,
            regime_risk=r.regime_risk,
            cri=r.cri,
            model_version=r.model_version,
        )
        for r in rows
    ]

