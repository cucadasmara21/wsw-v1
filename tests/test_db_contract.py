"""
DB contract tests: schema + API shape after init + seed.
Validates assets TABLE, assets_v8 VIEW, and endpoint stability.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from database import engine, init_database
from config import parse_db_scheme, settings


def _is_postgres() -> bool:
    return parse_db_scheme(settings.DATABASE_URL or "") == "postgresql"


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL")
def test_assets_endpoint_returns_200_after_seed(client: TestClient):
    """GET /api/assets must return 200 (no 500 from schema drift)."""
    from sqlalchemy.exc import OperationalError

    try:
        init_database()
        response = client.get("/api/assets?limit=10")
    except OperationalError:
        pytest.skip("Postgres not reachable")
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL")
def test_universe_tree_returns_at_least_2_groups_after_seed(client: TestClient):
    """GET /api/universe/tree must return >= 2 groups after deterministic seed."""
    from sqlalchemy.exc import OperationalError

    try:
        init_database()
        response = client.get("/api/universe/tree")
    except OperationalError:
        pytest.skip("Postgres not reachable")
    assert response.status_code == 200
    groups = response.json()["groups"]
    assert len(groups) >= 2, f"Expected >= 2 groups, got {len(groups)}"
