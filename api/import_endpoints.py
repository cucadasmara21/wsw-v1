"""
Import API - Bulk ontology and assets import

ADMIN-only endpoints for importing taxonomy structures.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import get_db
from models import User, Group, Subgroup, Category, Asset, CategoryAsset
from services.rbac_service import require_role, ROLE_ADMIN
from config import settings
from services import audit_service

router = APIRouter(tags=["import"])


class ImportPayload:
    """Represents bulk import structure"""
    def __init__(self, data: Dict[str, Any]):
        self.group = data.get("group", {})
        self.subgroups = data.get("subgroups", [])


@router.post("/taxonomy", summary="Bulk import taxonomy")
async def import_taxonomy(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ADMIN]))
):
    """
    Bulk import taxonomy (Groups → Subgroups → Categories → Assets)
    
    Structure:
    {
        "group": {"name": "Group 1", "code": "G1"},
        "subgroups": [
            {
                "name": "Subgroup 1", "code": "G1-S1",
                "categories": [
                    {
                        "name": "Category 1", "code": "G1-S1-C1",
                        "asset_type": "equity",
                        "assets": [
                            {"symbol": "AAPL", "name": "Apple Inc"},
                            {"symbol": "MSFT", "name": "Microsoft"}
                        ]
                    }
                ]
            }
        ]
    }
    
    Behavior:
    - Upsert by code (creates if not exists, updates if exists)
    - Assets upserted by symbol
    - Idempotent: same JSON twice = no duplication
    
    Returns:
        {
            "groups_created": int,
            "groups_updated": int,
            "subgroups_created": int,
            "subgroups_updated": int,
            "categories_created": int,
            "categories_updated": int,
            "assets_created": int,
            "assets_updated": int,
            "links_created": int,
            "errors": List[str]
        }
    """
    try:
        stats = {
            "groups_created": 0,
            "groups_updated": 0,
            "subgroups_created": 0,
            "subgroups_updated": 0,
            "categories_created": 0,
            "categories_updated": 0,
            "assets_created": 0,
            "assets_updated": 0,
            "links_created": 0,
            "errors": []
        }
        
        # 1. Import Group
        group_data = payload.get("group", {})
        if not group_data:
            raise ValueError("'group' field is required")
        
        group_code = group_data.get("code")
        group_name = group_data.get("name")
        if not group_code or not group_name:
            raise ValueError("group must have 'code' and 'name'")
        
        group = db.query(Group).filter(Group.name == group_code).first()
        if group:
            stats["groups_updated"] += 1
        else:
            group = Group(name=group_code)
            db.add(group)
            db.flush()
            stats["groups_created"] += 1
        
        # 2. Import Subgroups
        subgroups_data = payload.get("subgroups", [])
        for subgroup_data in subgroups_data:
            subgroup_code = subgroup_data.get("code")
            subgroup_name = subgroup_data.get("name")
            if not subgroup_code or not subgroup_name:
                stats["errors"].append(f"Subgroup missing code or name: {subgroup_data}")
                continue
            
            subgroup = db.query(Subgroup).filter(
                and_(
                    Subgroup.group_id == group.id,
                    Subgroup.name == subgroup_code
                )
            ).first()
            
            if subgroup:
                stats["subgroups_updated"] += 1
            else:
                subgroup = Subgroup(group_id=group.id, name=subgroup_code)
                db.add(subgroup)
                db.flush()
                stats["subgroups_created"] += 1
            
            # 3. Import Categories
            categories_data = subgroup_data.get("categories", [])
            for category_data in categories_data:
                category_code = category_data.get("code")
                category_name = category_data.get("name")
                asset_type = category_data.get("asset_type", "equity")
                
                if not category_code or not category_name:
                    stats["errors"].append(f"Category missing code or name: {category_data}")
                    continue
                
                category = db.query(Category).filter(
                    and_(
                        Category.subgroup_id == subgroup.id,
                        Category.name == category_code
                    )
                ).first()
                
                if category:
                    stats["categories_updated"] += 1
                else:
                    category = Category(subgroup_id=subgroup.id, name=category_code)
                    db.add(category)
                    db.flush()
                    stats["categories_created"] += 1
                
                # 4. Import Assets
                assets_data = category_data.get("assets", [])
                for asset_data in assets_data:
                    symbol = asset_data.get("symbol")
                    name = asset_data.get("name")
                    if not symbol or not name:
                        stats["errors"].append(f"Asset missing symbol or name: {asset_data}")
                        continue
                    
                    asset = db.query(Asset).filter(Asset.symbol == symbol).first()
                    
                    if asset:
                        # Update existing asset
                        asset.name = name
                        asset.category_id = category.id
                        stats["assets_updated"] += 1
                    else:
                        # Create new asset
                        asset = Asset(
                            symbol=symbol,
                            name=name,
                            category_id=category.id,
                            sector=asset_type
                        )
                        db.add(asset)
                        db.flush()
                        stats["assets_created"] += 1
                    
                    # Ensure CategoryAsset link exists (for selection tracking)
                    ca = db.query(CategoryAsset).filter(
                        and_(
                            CategoryAsset.category_id == category.id,
                            CategoryAsset.asset_id == asset.id
                        )
                    ).first()
                    
                    if not ca:
                        ca = CategoryAsset(
                            category_id=category.id,
                            asset_id=asset.id,
                            is_candidate=True
                        )
                        db.add(ca)
                        db.flush()
                        stats["links_created"] += 1
        
        db.commit()
        # Audit (best-effort)
        audit_service.log_action(
            action="import_taxonomy",
            entity_type="taxonomy",
            entity_id=None,
            metadata=stats,
            db=db,
            user=user,
        )
        return stats
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
