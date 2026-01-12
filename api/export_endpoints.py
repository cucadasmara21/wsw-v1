"""
Export API - Taxonomy export for admins
"""
from __future__ import annotations

from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User, Group, Subgroup, Category, Asset
from services.rbac_service import require_role, ROLE_ADMIN

router = APIRouter(tags=["export"])


def _export_group(group: Group) -> Dict[str, Any]:
    """Serialize a group with nested subgroups/categories/assets."""
    subgroups_payload: List[Dict[str, Any]] = []
    for sg in group.subgroups:
        categories_payload: List[Dict[str, Any]] = []
        for cat in sg.categories:
            assets_payload = [
                {"symbol": a.symbol, "name": a.name}
                for a in cat.assets
            ]
            asset_type = None
            if cat.assets:
                asset_type = cat.assets[0].sector or "equity"

            categories_payload.append(
                {
                    "name": cat.name,
                    "code": cat.name,
                    "asset_type": asset_type or "equity",
                    "assets": assets_payload,
                }
            )
        subgroups_payload.append(
            {
                "name": sg.name,
                "code": sg.name,
                "categories": categories_payload,
            }
        )
    return {"group": {"name": group.name, "code": group.name}, "subgroups": subgroups_payload}


@router.get("/taxonomy", summary="Export taxonomy structure")
async def export_taxonomy(
    db: Session = Depends(get_db),
    user: User = Depends(require_role([ROLE_ADMIN]))
):
    try:
        groups = db.query(Group).all()
        payloads = [_export_group(g) for g in groups]
        return {"items": payloads, "count": len(payloads)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")
