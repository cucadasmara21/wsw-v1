"""
Tests for paginated category assets endpoint
"""
import pytest
from fastapi.testclient import TestClient

from main import app
from models import Group, Subgroup, Category, Asset, User
from database import SessionLocal


class TestCategoryAssetsPagination:
    """Test paginated assets endpoint (/api/assets/category/{id}/paginated)"""
    
    @pytest.fixture(autouse=True)
    def setup(self, db_session, client):
        """Setup test data"""
        self.db = db_session
        self.client = client
        
        # Create test ontology and assets if they don't exist
        group = self.db.query(Group).filter(Group.name == "TestGroup").first()
        if not group:
            group = Group(name="TestGroup")
            self.db.add(group)
            self.db.flush()
        
        subgroup = self.db.query(Subgroup).filter(Subgroup.name == "TestSubgroup").first()
        if not subgroup:
            subgroup = Subgroup(group_id=group.id, name="TestSubgroup")
            self.db.add(subgroup)
            self.db.flush()
        
        category = self.db.query(Category).filter(Category.name == "TestCategory").first()
        if not category:
            category = Category(subgroup_id=subgroup.id, name="TestCategory")
            self.db.add(category)
            self.db.flush()
        
        self.category_id = category.id
        
        # Create test assets
        symbols = ["AAAA", "BBBB", "CCCC", "DDDD", "EEEE"]
        for i, symbol in enumerate(symbols):
            asset = self.db.query(Asset).filter(Asset.symbol == symbol).first()
            if not asset:
                asset = Asset(
                    symbol=symbol,
                    name=f"Company {chr(65+i)}",
                    category_id=self.category_id,
                    sector="Technology",
                    is_active=True
                )
                self.db.add(asset)
        
        self.db.commit()
    
    def test_assets_pagination_returns_items_and_meta(self):
        """Test that paginated endpoint returns items with pagination metadata"""
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        
        # Verify pagination
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert len(data["items"]) <= 2
        assert data["total"] >= 2  # At least 2 items from setup
    
    def test_assets_pagination_respects_limit(self):
        """Test that limit parameter is respected"""
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should return at most 2 items
        assert len(data["items"]) <= 2
    
    def test_assets_pagination_respects_offset(self):
        """Test that offset parameter works for pagination"""
        # Get first page
        resp1 = self.client.get(f"/api/assets/category/{self.category_id}/paginated?limit=2&offset=0")
        assert resp1.status_code == 200
        data1 = resp1.json()
        first_page = data1["items"]
        
        # Get second page
        resp2 = self.client.get(f"/api/assets/category/{self.category_id}/paginated?limit=2&offset=2")
        assert resp2.status_code == 200
        data2 = resp2.json()
        second_page = data2["items"]
        
        # Pages should be different if total > 2
        if data1["total"] > 2:
            assert first_page != second_page
    
    def test_assets_pagination_search_filters_results(self):
        """Test that search parameter filters by symbol or name"""
        # Search by symbol
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated?q=AAA")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should find at least AAAA
        assert data["total"] >= 1
        assert any(item["symbol"] == "AAAA" for item in data["items"])
    
    def test_assets_pagination_search_by_name(self):
        """Test that search works on name field"""
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated?q=Company")
        assert resp.status_code == 200
        data = resp.json()
        
        # Should find all company results
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
    
    def test_assets_pagination_nonexistent_category(self):
        """Test that nonexistent category returns 404"""
        resp = self.client.get("/api/assets/category/99999/paginated")
        assert resp.status_code == 404
    
    def test_assets_pagination_default_values(self):
        """Test that default limit and offset work"""
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated")
        assert resp.status_code == 200
        data = resp.json()
        
        # Check defaults: limit=50, offset=0
        assert data["limit"] == 50
        assert data["offset"] == 0
    
    def test_assets_pagination_max_limit_enforced(self):
        """Test that max limit of 500 is enforced"""
        # Try requesting more than max - FastAPI should reject with 422
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated?limit=1000")
        # FastAPI validates Query parameters, so 1000 > 500 results in validation error
        assert resp.status_code == 422  # Unprocessable Entity (validation error)
        
        # But limit=500 should work
        resp = self.client.get(f"/api/assets/category/{self.category_id}/paginated?limit=500")
        assert resp.status_code == 200
        data = resp.json()
        assert data["limit"] == 500
