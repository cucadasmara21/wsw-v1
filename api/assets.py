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
    existing = db.query(Asset).filter(Asset.symbol == asset_data. symbol).first()
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
