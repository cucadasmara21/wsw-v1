import pytest
from fastapi.testclient import TestClient

from main import app
from api.auth import get_current_user
from services.rbac_service import require_role
from database import SessionLocal
from models import Group, Subgroup, Category, Asset


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
    # Use real require_role logic; ensure override removed
    app.dependency_overrides.pop(require_role, None)
    app.dependency_overrides[get_current_user] = admin_dep


def clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(require_role, None)


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


def seed_taxonomy():
    session = SessionLocal()
    try:
        # Clean minimal subset to avoid duplicates
        session.query(Asset).delete()
        session.query(Category).delete()
        session.query(Subgroup).delete()
        session.query(Group).delete()
        session.commit()

        group = Group(name="EXP-G")
        session.add(group)
        session.flush()

        sg = Subgroup(name="EXP-SG", group_id=group.id)
        session.add(sg)
        session.flush()

        cat = Category(name="EXP-C", subgroup_id=sg.id)
        session.add(cat)
        session.flush()

        asset = Asset(symbol="EXP1", name="Export Asset", category_id=cat.id, sector="equity")
        session.add(asset)
        session.commit()
    finally:
        session.close()


def test_export_taxonomy_as_admin():
    set_admin_user()
    seed_taxonomy()

    with TestClient(app) as client:
        resp = client.get("/api/export/taxonomy")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["count"] >= 1
        payloads = data["items"]
        target = next((p for p in payloads if p.get("group", {}).get("code") == "EXP-G"), None)
        assert target is not None
        assert target["group"]["name"] == "EXP-G"
        subgroups = target.get("subgroups", [])
        assert len(subgroups) == 1
        categories = subgroups[0].get("categories", [])
        assert len(categories) == 1
        assets = categories[0].get("assets", [])
        assert any(a["symbol"] == "EXP1" for a in assets)

    restore_test_overrides()


def test_export_taxonomy_requires_admin():
    clear_overrides()
    with TestClient(app) as client:
        resp = client.get("/api/export/taxonomy")
        assert resp.status_code in (401, 403)
    restore_test_overrides()
