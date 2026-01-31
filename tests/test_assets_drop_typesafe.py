"""
Test type-safe drop helper (drop_relation_type_safe).
Uses temp relation __ci_drop_test_assets to avoid touching production public.assets.
"""
import pytest
from sqlalchemy import text

from database import engine, drop_relation_type_safe, init_database
from config import parse_db_scheme, settings


_CI_TEST_REL = "public.__ci_drop_test_assets"


@pytest.fixture(scope="module", autouse=True)
def _restore_schema_after_module():
    yield
    try:
        init_database()
    except Exception:
        pass


def _is_postgres() -> bool:
    return parse_db_scheme(settings.DATABASE_URL or "") == "postgresql"


def _to_regclass_is_null(rel: str) -> bool:
    with engine.connect() as conn:
        r = conn.execute(text(f"SELECT to_regclass('{rel}') IS NULL")).scalar()
        return bool(r)


def _drop_temp_if_exists(conn) -> None:
    """Clean up temp relation using type-safe drop."""
    drop_relation_type_safe(conn, "public", "__ci_drop_test_assets")


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL (DATABASE_URL)")
def test_drop_relation_table():
    """Create TABLE temp, run drop_relation_type_safe, assert gone."""
    from sqlalchemy.exc import OperationalError

    try:
        with engine.begin() as conn:
            _drop_temp_if_exists(conn)
            conn.execute(
                text(
                    f"CREATE TABLE {_CI_TEST_REL} (id serial PRIMARY KEY, symbol text);"
                )
            )
        assert not _to_regclass_is_null(_CI_TEST_REL)

        with engine.begin() as conn:
            drop_relation_type_safe(conn, "public", "__ci_drop_test_assets")
        assert _to_regclass_is_null(_CI_TEST_REL)
    except OperationalError:
        pytest.skip("Postgres not reachable")


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL (DATABASE_URL)")
def test_drop_relation_view():
    """Create VIEW temp, run drop_relation_type_safe, assert gone."""
    from sqlalchemy.exc import OperationalError

    try:
        with engine.begin() as conn:
            _drop_temp_if_exists(conn)
            conn.execute(
                text(
                    f"CREATE VIEW {_CI_TEST_REL} AS SELECT 1 AS id, 'x'::text AS symbol;"
                )
            )
        assert not _to_regclass_is_null(_CI_TEST_REL)

        with engine.begin() as conn:
            drop_relation_type_safe(conn, "public", "__ci_drop_test_assets")
        assert _to_regclass_is_null(_CI_TEST_REL)
    except OperationalError:
        pytest.skip("Postgres not reachable")


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL (DATABASE_URL)")
def test_drop_relation_noop_when_missing():
    """When relation does not exist, drop is no-op, no exception."""
    from sqlalchemy.exc import OperationalError

    try:
        with engine.begin() as conn:
            _drop_temp_if_exists(conn)
            drop_relation_type_safe(conn, "public", "__ci_drop_test_assets")
        assert _to_regclass_is_null(_CI_TEST_REL)
    except OperationalError:
        pytest.skip("Postgres not reachable")
