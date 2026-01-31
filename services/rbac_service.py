"""
Role-Based Access Control (RBAC) service
Defines roles and dependencies for FastAPI
"""
from typing import List, Optional
from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from api.auth import get_current_user
from models import User
from config import settings

# Define valid roles
ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
ROLE_VIEWER = "viewer"

VALID_ROLES = [ROLE_ADMIN, ROLE_ANALYST, ROLE_VIEWER]

# Role hierarchy: admin > analyst > viewer
ROLE_HIERARCHY = {
    ROLE_ADMIN: 3,
    ROLE_ANALYST: 2,
    ROLE_VIEWER: 1,
}


def require_role(allowed_roles: List[str]):
    """
    Dependency factory that ensures user has one of the allowed roles.
    
    Usage:
        @router.get("/admin-endpoint")
        async def admin_endpoint(user: User = Depends(require_role([ROLE_ADMIN]))):
            ...
    """
    async def check_role(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. Required role: {', '.join(allowed_roles)}, got {current_user.role}"
            )
        return current_user
    
    return check_role


def has_role_or_higher(required_role: str):
    """
    Dependency that checks if user has the required role or higher in hierarchy.
    
    Example: has_role_or_higher(ROLE_ANALYST) allows admin + analyst
    """
    async def check_hierarchy(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ) -> User:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 0)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {required_role}"
            )
        return current_user
    
    return check_hierarchy
