"""
Database schema contract tests: Verify required tables exist
"""
import pytest
from sqlalchemy import inspect, text
from database import engine, Base
from models import Asset, Price, RiskSnapshot, Category, Group, Subgroup


def test_required_tables_exist():
    """Verify all required tables exist after init_database(); assets must be TABLE (insertable)."""
    from database import init_database
    init_database()

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    required_tables = [
        "assets",
        "prices",
        "users",
        "risk_metrics",
    ]

    for table in required_tables:
        assert table in tables, f"Required table '{table}' missing"

    # assets must be TABLE (not VIEW) for legacy inserts
    with engine.connect() as conn:
        r = conn.execute(
            text(
                "SELECT relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relname = 'assets'"
            )
        ).scalar()
    assert r == "r", "public.assets must be TABLE (relkind='r'), not VIEW"

    # Taxonomy tables may not exist if DB not initialized with seed_ontology
    # But if they exist, they must have correct structure
    if "risk_snapshots" in tables:
        # Verify RiskSnapshot has required columns for TaxonomyEngine
        columns = [col["name"] for col in inspector.get_columns("risk_snapshots")]
        assert "asset_id" in columns
        assert "ts" in columns
        assert "cri" in columns  # Used by compute_risk01()


def test_risk_snapshot_schema():
    """Verify RiskSnapshot model matches TaxonomyEngine expectations"""
    from models import RiskSnapshot
    
    # Verify model has required attributes
    assert hasattr(RiskSnapshot, "asset_id")
    assert hasattr(RiskSnapshot, "ts")
    assert hasattr(RiskSnapshot, "cri")
    assert hasattr(RiskSnapshot, "price_risk")
    assert hasattr(RiskSnapshot, "liq_risk")
    assert hasattr(RiskSnapshot, "fund_risk")
    assert hasattr(RiskSnapshot, "cp_risk")
    assert hasattr(RiskSnapshot, "regime_risk")


def test_asset_category_relationship():
    """Verify Asset-Category relationship exists (required by TaxonomyEngine)"""
    from models import Asset, Category
    
    # Verify relationship exists
    assert hasattr(Asset, "category_id")
    assert hasattr(Category, "id")
    
    # Verify Asset model can query Category
    # (This is a structural test, not a runtime test)


def test_assets_v8_view_creatable():
    """Verify public.assets_v8 view exists when universe_assets is present (Route A)."""
    from database import init_database
    from config import parse_db_scheme, settings
    from sqlalchemy.exc import OperationalError

    if parse_db_scheme(settings.DATABASE_URL or "") != "postgresql":
        pytest.skip("Requires PostgreSQL")
    try:
        init_database()
        with engine.connect() as conn:
            v = conn.execute(
                text("SELECT to_regclass('public.assets_v8') IS NOT NULL")
            ).scalar()
    except OperationalError:
        pytest.skip("Postgres not reachable")
    assert v, "public.assets_v8 view should exist after init"
