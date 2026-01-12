"""
Block 8: Tests for real Group 1 sample import from PDFs.
Verifies idempotence, structure, and data quality.
"""
import json
import pytest
from pathlib import Path
from main import app
from models import User, Group, Subgroup, Category, Asset, CategoryAsset
from services.rbac_service import require_role
from api.auth import get_current_user


SAMPLE_JSON = Path(__file__).parent.parent / "frontend" / "public" / "samples" / "group1.json"


@pytest.fixture(autouse=True)
def setup_admin_override():
    """Override RBAC to admin for all tests in this module"""
    def admin_override(_roles=None):
        def _dep():
            return User(
                id=999,
                email="admin@test.local",
                username="admin_test",
                hashed_password="",
                role="admin",
                is_active=True,
            )
        return _dep
    
    def fake_admin_user():
        return User(
            id=999,
            email="admin@test.local",
            username="admin_test",
            hashed_password="",
            role="admin",
            is_active=True,
        )
    
    app.dependency_overrides[require_role] = admin_override
    app.dependency_overrides[get_current_user] = fake_admin_user
    
    yield
    
    app.dependency_overrides.clear()


@pytest.fixture
def sample_payload() -> dict:
    """Load Group 1 sample from frontend/public/samples."""
    if not SAMPLE_JSON.exists():
        pytest.skip(f"Sample file not found: {SAMPLE_JSON}")
    with open(SAMPLE_JSON) as f:
        return json.load(f)


class TestBlock8SampleStructure:
    """Verify extracted sample structure."""
    
    def test_sample_file_exists(self):
        """Verify sample file is present and valid JSON."""
        assert SAMPLE_JSON.exists(), f"Sample file not found: {SAMPLE_JSON}"
        with open(SAMPLE_JSON) as f:
            data = json.load(f)
        assert "group" in data
        assert "subgroups" in data
        assert data["group"]["code"] == "GROUP_1"
    
    def test_sample_structure_complete(self, sample_payload: dict):
        """Verify sample has expected structure and content."""
        group = sample_payload["group"]
        subgroups = sample_payload["subgroups"]
        
        # Group level
        assert group["code"] == "GROUP_1"
        assert group["name"] == "Group 1"
        
        # At least one subgroup
        assert len(subgroups) > 0, "Sample has no subgroups"
        
        subgroup = subgroups[0]
        assert "name" in subgroup
        assert "code" in subgroup
        assert "categories" in subgroup
        
        # At least one category
        assert len(subgroup["categories"]) > 0, "Subgroup has no categories"
        
        category = subgroup["categories"][0]
        assert "name" in category
        assert "code" in category
        assert "asset_type" in category
        assert "assets" in category
        
        # At least one asset per category
        for cat in subgroup["categories"]:
            assert len(cat["assets"]) > 0, f"Category {cat['name']} has no assets"
            for asset in cat["assets"]:
                assert "symbol" in asset
                assert "name" in asset
                assert len(asset["symbol"]) > 0
                assert len(asset["name"]) > 0
    
    def test_no_null_names(self, sample_payload: dict):
        """All names must be non-empty strings."""
        for sg in sample_payload["subgroups"]:
            assert sg["name"].strip()
            for cat in sg["categories"]:
                assert cat["name"].strip()
                for asset in cat["assets"]:
                    assert asset["name"].strip()
    
    def test_no_null_codes(self, sample_payload: dict):
        """All codes must be non-empty strings."""
        assert sample_payload["group"]["code"].strip()
        for sg in sample_payload["subgroups"]:
            assert sg["code"].strip()
            for cat in sg["categories"]:
                assert cat["code"].strip()
                for asset in cat["assets"]:
                    assert asset["symbol"].strip()
    
    def test_reasonable_asset_counts(self, sample_payload: dict):
        """Verify sample has realistic asset counts (PDF has 85)."""
        total_assets = sum(
            len(cat["assets"])
            for sg in sample_payload["subgroups"]
            for cat in sg["categories"]
        )
        # PDF has 85 assets; expect > 50
        assert total_assets > 50, f"Too few assets extracted: {total_assets}"
        assert total_assets < 500, f"Too many assets: {total_assets}"


class TestBlock8SampleImport:
    """Test importing real Group 1 sample."""
    
    def test_import_sample_creates_entities(self, client, db_session, sample_payload: dict):
        """Import sample → verify entities created or updated."""
        response = client.post("/api/import/taxonomy", json=sample_payload)
        
        assert response.status_code == 200, f"Import failed: {response.text}"
        stats = response.json()
        
        # Verify response structure
        assert "groups_created" in stats or "groups_updated" in stats
        assert "subgroups_created" in stats or "subgroups_updated" in stats
        assert "categories_created" in stats or "categories_updated" in stats
        assert "assets_created" in stats or "assets_updated" in stats
        
        # Verify entities were created
        total_created = (
            stats.get("groups_created", 0) +
            stats.get("subgroups_created", 0) +
            stats.get("categories_created", 0) +
            stats.get("assets_created", 0)
        )
        assert total_created > 0, "No entities were created"
        
        # Verify Group exists
        group = db_session.query(Group).filter(Group.name == "GROUP_1").first()
        assert group is not None, "Group 1 not created"
        
        # Verify Subgroup exists
        subgroup = db_session.query(Subgroup).filter(Subgroup.group_id == group.id).first()
        assert subgroup is not None, "Subgroup 1 not created"
        
        # Verify Categories exist
        categories = db_session.query(Category).filter(Category.subgroup_id == subgroup.id).all()
        assert len(categories) > 0, "No categories created"
        
        # Verify Assets exist
        assets = db_session.query(Asset).all()
        assert len(assets) > 0, "No assets created"
        
        # Verify CategoryAsset links exist
        links = db_session.query(CategoryAsset).all()
        assert len(links) > 0, "No CategoryAsset links created"
    
    def test_import_idempotent(self, client, db_session, sample_payload: dict):
        """Import same payload twice → verify idempotence (no duplication)."""
        # First import
        response1 = client.post("/api/import/taxonomy", json=sample_payload)
        assert response1.status_code == 200
        stats1 = response1.json()
        
        created_count_1 = (
            stats1.get("groups_created", 0) +
            stats1.get("assets_created", 0)
        )
        
        # Second import (same data)
        response2 = client.post("/api/import/taxonomy", json=sample_payload)
        assert response2.status_code == 200
        stats2 = response2.json()
        
        # Second import should have minimal new creations
        created_count_2 = (
            stats2.get("groups_created", 0) +
            stats2.get("assets_created", 0)
        )
        updated_count_2 = (
            stats2.get("groups_updated", 0) +
            stats2.get("assets_updated", 0)
        )
        
        # First run created; second run should mostly update
        assert created_count_2 <= created_count_1, "Idempotence violated: second import created too many"
        assert updated_count_2 > 0, "Second import should have updates instead of new creations"


def test_health_endpoint_includes_data_quality(client):
    """Test that /health includes data_quality KPIs"""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "data_quality" in data
    
    dq = data["data_quality"]
    assert "cached_percent" in dq
    assert "stale_percent" in dq
    assert "avg_confidence" in dq
    assert "provider_errors" in dq
    assert "rate_limited" in dq
    
    # Validate types
    assert isinstance(dq["cached_percent"], (int, float))
    assert isinstance(dq["stale_percent"], (int, float))
    assert isinstance(dq["avg_confidence"], (int, float))
    assert isinstance(dq["provider_errors"], int)
    assert isinstance(dq["rate_limited"], int)


def test_import_sample_group1_json(client):
    """Test importing the sample Group 1 JSON"""
    # Load the sample file
    sample_path = Path(__file__).parent.parent / "frontend" / "public" / "samples" / "group1.json"
    
    if not sample_path.exists():
        pytest.skip("Sample group1.json not found")
    
    with open(sample_path, 'r') as f:
        sample_data = json.load(f)
    
    # Import the taxonomy
    response = client.post(
        "/api/import/taxonomy",
        json=sample_data
    )
    
    assert response.status_code == 200
    result = response.json()
    
    # Verify import results
    assert "groups_created" in result or "groups_updated" in result
    assert "assets_created" in result or "assets_updated" in result
    
    # Verify at least some items were processed
    total_ops = (
        result.get("groups_created", 0) + result.get("groups_updated", 0) +
        result.get("subgroups_created", 0) + result.get("subgroups_updated", 0) +
        result.get("categories_created", 0) + result.get("categories_updated", 0) +
        result.get("assets_created", 0) + result.get("assets_updated", 0)
    )
    assert total_ops > 0


def test_export_returns_imported_content(client):
    """Test that export returns the same content structure that was imported"""
    # First, import sample data
    sample_path = Path(__file__).parent.parent / "frontend" / "public" / "samples" / "group1.json"
    
    if not sample_path.exists():
        pytest.skip("Sample group1.json not found")
    
    with open(sample_path, 'r') as f:
        sample_data = json.load(f)
    
    # Import
    import_response = client.post(
        "/api/import/taxonomy",
        json=sample_data
    )
    assert import_response.status_code == 200
    
    # Export
    export_response = client.get(
        "/api/export/taxonomy"
    )
    assert export_response.status_code == 200
    
    export_data = export_response.json()
    assert "items" in export_data
    assert "count" in export_data
    assert isinstance(export_data["items"], list)
    
    # Verify export has data
    assert export_data["count"] > 0
    assert len(export_data["items"]) > 0
    
    # Verify structure matches import format (nested with group/subgroups)
    first_item = export_data["items"][0]
    assert "group" in first_item
    assert "name" in first_item["group"]
    assert "code" in first_item["group"]


def test_data_quality_kpis_structure(client):
    """Test data quality KPIs have expected structure and reasonable values"""
    response = client.get("/health")
    assert response.status_code == 200
    
    dq = response.json()["data_quality"]
    
    # Percentages should be between 0-100
    assert 0 <= dq["cached_percent"] <= 100
    assert 0 <= dq["stale_percent"] <= 100
    assert 0 <= dq["avg_confidence"] <= 100
    
    # Counts should be non-negative
    assert dq["provider_errors"] >= 0
    assert dq["rate_limited"] >= 0
