"""
Pytest configuration and fixtures
Provides TestClient for FastAPI app testing
"""
import pytest
from typing import Generator
from fastapi.testclient import TestClient

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings
from config import parse_db_scheme

from main import app
from services.rbac_service import require_role
from api.auth import get_current_user


@pytest.fixture(autouse=True)
def _reset_postgres_schema_per_test():
    """Reset Postgres schema between tests to avoid contamination (UniqueViolation, etc.)."""
    if parse_db_scheme(settings.DATABASE_URL or "") != "postgresql":
        yield
        return
    try:
        from database import engine, init_database
        from sqlalchemy import text

        with engine.connect() as conn:
            r = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in r.fetchall()]
        if tables:
            with engine.begin() as conn:
                tbl_list = ", ".join(f'public."{t}"' for t in tables)
                conn.execute(text(f"TRUNCATE TABLE {tbl_list} RESTART IDENTITY CASCADE"))
        init_database()
        try:
            from seed_ontology import seed_ontology
            seed_ontology()
        except Exception:
            pass
    except Exception:
        pass
    yield


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    """Create TestClient for the FastAPI app"""
    # Note: Uses the app's default database (wsw.db)
    # Tests should be tolerant of database state
    # Override RBAC in tests to allow unauthenticated access
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

    # Allow any role and bypass JWT in tests
    app.dependency_overrides[require_role] = allow_all
    def fake_current_user():
        from models import User
        return User(
            id=0,
            email="test@local",
            username="tester",
            hashed_password="",
            role="viewer",
            is_active=True,
        )
    app.dependency_overrides[get_current_user] = fake_current_user
    with TestClient(app) as test_client:
        # Seed ontology so universe tree tests have data
        try:
            from seed_ontology import seed_ontology
            seed_ontology()
        except Exception:
            # If seeding fails, continue; some tests tolerate empty state
            pass
        yield test_client
