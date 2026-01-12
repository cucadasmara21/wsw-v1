from __future__ import annotations

"""
Universe API - Navegación de ontología
"""
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from database import get_db
from models import Group, Subgroup, Category
from schemas import (
    UniverseTreeResponse,
    GroupNode,
    SubgroupNode,
    CategoryNode,
)

router = APIRouter(tags=["universe"])


@router.get("/tree", response_model=UniverseTreeResponse, summary="Get universe tree")
async def get_universe_tree(db: Session = Depends(get_db)):
    """
    Return complete ontology tree: Groups → Subgroups → Categories
    
    This endpoint is optimized with eager loading to minimize queries.
    Use it to populate navigation UI.
    """
    groups = (
        db.query(Group)
        .options(
            joinedload(Group.subgroups).joinedload(Subgroup.categories)
        )
        .order_by(Group.name)
        .all()
    )
    
    tree_nodes = []
    for group in groups:
        subgroup_nodes = []
        for subgroup in sorted(group.subgroups, key=lambda x: x.name):
            category_nodes = [
                CategoryNode(id=cat.id, name=cat.name)
                for cat in sorted(subgroup.categories, key=lambda x: x.name)
            ]
            subgroup_nodes.append(
                SubgroupNode(
                    id=subgroup.id,
                    name=subgroup.name,
                    categories=category_nodes
                )
            )
        
        tree_nodes.append(
            GroupNode(
                id=group.id,
                name=group.name,
                subgroups=subgroup_nodes
            )
        )
    
    return UniverseTreeResponse(groups=tree_nodes)
