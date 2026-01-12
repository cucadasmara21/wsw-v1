from fastapi.testclient import TestClient

from main import app
from api.auth import get_current_user
from services.rbac_service import require_role
from database import SessionLocal
from models import AuditLog


def set_admin_user():
    def admin_dep():
        from models import User
        return User(
            id=1,
            email="admin@test",
            username="admin",
            hashed_password="",
            role="admin",
            is_active=True,
        )
    app.dependency_overrides.pop(require_role, None)
    app.dependency_overrides[get_current_user] = admin_dep


def restore_test_overrides():
    def allow_all(_roles=None):
        def _dep():
            from models import User
            return User(
                id=0,
                email="test@local",
                username="tester",
                hashed_password="",
                role="viewer",
                is_active=True,
            )
        return _dep

    def fake_user():
        from models import User
        return User(
            id=0,
            email="test@local",
            username="tester",
            hashed_password="",
            role="viewer",
            is_active=True,
        )

    app.dependency_overrides[require_role] = allow_all
    app.dependency_overrides[get_current_user] = fake_user


def test_audit_log_created_on_import():
    set_admin_user()
    payload = {
        "group": {"name": "AUDIT-G", "code": "AUDIT-G"},
        "subgroups": [
            {
                "name": "AUDIT-SG",
                "code": "AUDIT-SG",
                "categories": [
                    {
                        "name": "AUDIT-CAT",
                        "code": "AUDIT-CAT",
                        "asset_type": "equity",
                        "assets": [
                            {"symbol": "AUD1", "name": "Audit Asset"}
                        ],
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        resp = client.post("/api/import/taxonomy", json=payload)
        assert resp.status_code == 200

    session = SessionLocal()
    try:
        audit_rows = session.query(AuditLog).filter(AuditLog.action == "import_taxonomy").all()
        assert len(audit_rows) >= 1
    finally:
        session.close()
        restore_test_overrides()
