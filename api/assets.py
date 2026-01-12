from __future__ import annotations

"""
Endpoints para gestión de activos con ontología
RBAC-protected endpoints
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_

from database import get_db
from models import Asset, Category, Subgroup, Group, User
from schemas import Asset as AssetSchema, AssetCreate, AssetUpdate, AssetDetail
from services.rbac_service import require_role, has_role_or_higher, ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN

router = APIRouter(tags=["assets"])


@router.get("/", response_model=List[AssetSchema], summary="List assets with filters")
async def get_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(True),
    group_id: Optional[int] = Query(None, description="Filter by group ID"),
    subgroup_id: Optional[int] = Query(None, description="Filter by subgroup ID"),
    category_id: Optional[int] = Query(None, description="Filter by category ID"),
    q: Optional[str] = Query(None, description="Search by symbol or name"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    List assets with ontology filters and search.
    
    Filters can be combined:
    - **group_id**: Filter assets in specific group
    - **subgroup_id**: Filter assets in specific subgroup
    - **category_id**: Filter assets in specific category
    - **q**: Search by symbol or name (case-insensitive)
    """
    query = db.query(Asset)
    
    if active_only:
        query = query.filter(Asset.is_active == True)
    
    # Ontology filters
    if category_id is not None:
        query = query.filter(Asset.category_id == category_id)
    elif subgroup_id is not None:
        # Filter by subgroup: join to categories
        query = query.join(Category).filter(Category.subgroup_id == subgroup_id)
    elif group_id is not None:
        # Filter by group: join through categories and subgroups
        query = query.join(Category).join(Subgroup).filter(Subgroup.group_id == group_id)
    
    # Text search
    if q:
        search_pattern = f"%{q}%"
        query = query.filter(
            or_(
                Asset.symbol.ilike(search_pattern),
                Asset.name.ilike(search_pattern)
            )
        )
    
    assets = query.order_by(Asset.symbol).offset(skip).limit(limit).all()
    return assets


@router.get("/{asset_id}", response_model=AssetDetail, summary="Get asset detail")
async def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_VIEWER, ROLE_ANALYST, ROLE_ADMIN]))
):
    """
    Get detailed asset information including category hierarchy.
    """
    asset = (
        db.query(Asset)
        .options(
            joinedload(Asset.category_rel)
            .joinedload(Category.subgroup)
            .joinedload(Subgroup.group)
        )
        .filter(Asset.id == asset_id)
        .first()
    )
    
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    
    # Build response with category info
    response_data = {
        "id": asset.id,
        "symbol": asset.symbol,
        "name": asset.name,
        "sector": asset.sector,
        "category_id": asset.category_id,
        "exchange": asset.exchange,
        "country": asset.country,
        "is_active": asset.is_active,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
        "category_name": None,
        "subgroup_name": None,
        "group_name": None,
    }
    
    if asset.category_rel:
        response_data["category_name"] = asset.category_rel.name
        if asset.category_rel.subgroup:
            response_data["subgroup_name"] = asset.category_rel.subgroup.name
            if asset.category_rel.subgroup.group:
                response_data["group_name"] = asset.category_rel.subgroup.group.name
    
    return AssetDetail(**response_data)


@router.post("/", response_model=AssetSchema, status_code=201)
async def create_asset(
    asset_data: AssetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ADMIN]))
):
    """Create new asset"""
    existing = db.query(Asset).filter(Asset.symbol == asset_data.symbol).first()
    if existing:
        raise HTTPException(status_code=400, detail="Asset with this symbol already exists")

    db_asset = Asset(**asset_data.model_dump())
    db.add(db_asset)
    db.commit()
    db.refresh(db_asset)
    return db_asset

