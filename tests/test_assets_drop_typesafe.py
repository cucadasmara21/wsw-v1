"""
Test type-safe drop of public.assets (VIEW or TABLE).
Uses same DB engine as CI (DATABASE_URL).
"""
import pytest
from sqlalchemy import text

from database import engine, drop_public_assets_type_safe, init_database
from config import parse_db_scheme, settings


@pytest.fixture(scope="module", autouse=True)
def _restore_schema_after_module():
    yield
    try:
        init_database()
    except Exception:
        pass


def _is_postgres() -> bool:
    dsn = settings.DATABASE_URL or ""
    return parse_db_scheme(dsn) == "postgresql"


def _to_regclass_is_null() -> bool:
    with engine.connect() as conn:
        r = conn.execute(text("SELECT to_regclass('public.assets') IS NULL")).scalar()
        return bool(r)


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL (DATABASE_URL)")
def test_drop_public_assets_table():
    """Create TABLE public.assets, run drop helper, assert to_regclass is NULL."""
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS public.assets CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS public.assets CASCADE;"))
        conn.execute(
            text(
                "CREATE TABLE public.assets (id serial PRIMARY KEY, symbol text);"
            )
        )
    assert not _to_regclass_is_null()

    with engine.begin() as conn:
        drop_public_assets_type_safe(conn)
    assert _to_regclass_is_null()


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL (DATABASE_URL)")
def test_drop_public_assets_view():
    """Create VIEW public.assets, run drop helper, assert to_regclass is NULL."""
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS public.assets CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS public.assets CASCADE;"))
        conn.execute(
            text("CREATE VIEW public.assets AS SELECT 1 AS id, 'x'::text AS symbol;")
        )
    assert not _to_regclass_is_null()

    with engine.begin() as conn:
        drop_public_assets_type_safe(conn)
    assert _to_regclass_is_null()


@pytest.mark.skipif(not _is_postgres(), reason="Requires PostgreSQL (DATABASE_URL)")
def test_drop_public_assets_noop_when_missing():
    """When public.assets does not exist, drop is no-op."""
    with engine.begin() as conn:
        conn.execute(text("DROP VIEW IF EXISTS public.assets CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS public.assets CASCADE;"))
        drop_public_assets_type_safe(conn)
    assert _to_regclass_is_null()
