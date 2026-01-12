"""
Block 7: Tests for sample Group 1 import/export and data quality KPIs
"""
import json
import pytest
from pathlib import Path
from main import app
from models import User
from services.rbac_service import require_role
from api.auth import get_current_user


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
