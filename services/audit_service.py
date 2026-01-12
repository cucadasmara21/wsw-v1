"""
Audit logging helper
Captures minimal context for sensitive actions without failing main flow.
"""
from __future__ import annotations

from typing import Any, Optional
from sqlalchemy.orm import Session

from database import SessionLocal
from models import AuditLog, User


def log_action(
    action: str,
    entity_type: str,
    entity_id: Optional[str | int] = None,
    metadata: Optional[dict[str, Any]] = None,
    *,
    db: Session | None = None,
    user: User | None = None,
    request_id: Optional[str] = None,
    ip: Optional[str] = None,
) -> None:
    """Persist a minimal audit entry. Swallows errors to avoid impacting main flow."""
    session = db or SessionLocal()
    close_session = db is None
    try:
        entry = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            metadata_json=metadata or {},
            actor_user_id=getattr(user, "id", None),
            request_id=request_id,
            ip=ip,
        )
        session.add(entry)
        session.commit()
    except Exception:
        # Do not propagate audit errors
        if not close_session:
            session.rollback()
    finally:
        if close_session:
            session.close()
