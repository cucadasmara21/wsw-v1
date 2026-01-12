"""
Tests for universe API endpoints
"""
import pytest
from fastapi.testclient import TestClient


def test_universe_tree(client: TestClient):
    """Test GET /api/universe/tree returns valid tree structure"""
    response = client.get("/api/universe/tree")
    assert response.status_code == 200
    
    data = response.json()
    assert "groups" in data
    assert isinstance(data["groups"], list)
    
    # Verify structure
    if len(data["groups"]) > 0:
        group = data["groups"][0]
        assert "id" in group
        assert "name" in group
        assert "subgroups" in group
        assert isinstance(group["subgroups"], list)
        
        if len(group["subgroups"]) > 0:
            subgroup = group["subgroups"][0]
            assert "id" in subgroup
            assert "name" in subgroup
            assert "categories" in subgroup
            assert isinstance(subgroup["categories"], list)


def test_universe_tree_with_seed_data(client: TestClient):
    """Test tree contains expected seeded data"""
    response = client.get("/api/universe/tree")
    assert response.status_code == 200
    
    data = response.json()
    groups = data["groups"]
    
    # Should have at least 2 groups from seed
    assert len(groups) >= 2
    
    # Find Equities group
    equities = next((g for g in groups if g["name"] == "Equities"), None)
    assert equities is not None
    assert len(equities["subgroups"]) >= 2
    
    # Find US Tech subgroup
    us_tech = next((sg for sg in equities["subgroups"] if sg["name"] == "US Tech"), None)
    assert us_tech is not None
    assert len(us_tech["categories"]) >= 2


def test_assets_filter_by_category(client: TestClient):
    """Test GET /api/assets?category_id=X filters correctly"""
    # First get tree to find a category ID
    tree_response = client.get("/api/universe/tree")
    tree = tree_response.json()
    
    if len(tree["groups"]) > 0:
        first_category = tree["groups"][0]["subgroups"][0]["categories"][0]
        category_id = first_category["id"]
        
        # Filter assets by this category
        response = client.get(f"/api/assets/?category_id={category_id}")
        assert response.status_code == 200
        
        assets = response.json()
        assert isinstance(assets, list)
        
        # All assets should belong to this category
        for asset in assets:
            assert asset["category_id"] == category_id


def test_assets_search(client: TestClient):
    """Test GET /api/assets?q=AAPL searches correctly"""
    response = client.get("/api/assets/?q=AAPL")
    assert response.status_code == 200
    
    assets = response.json()
    assert isinstance(assets, list)
    
    # Should find AAPL if seeded
    if len(assets) > 0:
        aapl = next((a for a in assets if a["symbol"] == "AAPL"), None)
        assert aapl is not None
        assert "Apple" in aapl["name"]


def test_asset_detail_with_hierarchy(client: TestClient):
    """Test GET /api/assets/{id} returns category hierarchy"""
    # Get first asset from list
    list_response = client.get("/api/assets/?limit=1")
    assets = list_response.json()
    
    if len(assets) > 0:
        asset_id = assets[0]["id"]
        
        # Get detail
        response = client.get(f"/api/assets/{asset_id}")
        assert response.status_code == 200
        
        detail = response.json()
        assert "id" in detail
        assert "symbol" in detail
        assert "category_name" in detail
        assert "subgroup_name" in detail
        assert "group_name" in detail


def test_asset_detail_not_found(client: TestClient):
    """Test GET /api/assets/{id} returns 404 for invalid ID"""
    response = client.get("/api/assets/999999")
    assert response.status_code == 404
