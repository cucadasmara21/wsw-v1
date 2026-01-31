"""
Database schema contract tests: Verify required tables exist
"""
import pytest
from sqlalchemy import inspect, text
from database import engine, Base
from models import Asset, Price, RiskSnapshot, Category, Group, Subgroup


def test_required_tables_exist():
    """Verify all required tables and public.assets VIEW exist after init_database()"""
    from database import init_database
    init_database()

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    # Core tables (Route A: assets is VIEW, not table)
    required_tables = [
        "prices",
        "users",
        "risk_metrics",
    ]

    for table in required_tables:
        assert table in tables, f"Required table '{table}' missing"

    # Route A: public.assets must exist as VIEW (compatibility layer)
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('public.assets') IS NOT NULL")
        ).scalar()
    assert exists, "Required view 'public.assets' missing"
    
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
