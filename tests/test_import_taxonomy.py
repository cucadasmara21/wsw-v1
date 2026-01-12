"""
Tests for bulk taxonomy import endpoint
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from main import app
from models import Group, Subgroup, Category, Asset, CategoryAsset, User
from database import SessionLocal
from services.rbac_service import require_role
from api.auth import get_current_user


class TestImportTaxonomy:
    """Test bulk import endpoint (/api/import/taxonomy)"""
    
    @pytest.fixture(autouse=True)
    def setup(self, db_session, client):
        """Setup before each test - override RBAC to admin"""
        self.db = db_session
        self.client = client
        
        # Override RBAC to provide admin user for import tests
        def admin_override(_roles=None):
            def _dep():
                return User(
                    id=0,
                    email="admin@test.local",
                    username="admin",
                    hashed_password="",
                    role="admin",
                    is_active=True,
                )
            return _dep
        
        # Also override get_current_user directly
        def fake_admin_user():
            return User(
                id=0,
                email="admin@test.local",
                username="admin",
                hashed_password="",
                role="admin",
                is_active=True,
            )
        
        app.dependency_overrides[require_role] = admin_override
        app.dependency_overrides[get_current_user] = fake_admin_user
        
        yield
        
        # Cleanup: reset overrides for next test
        app.dependency_overrides.clear()
    
    def test_import_idempotent_no_duplicates(self, db_session):
        """
        Test idempotent import: Same JSON twice should not create duplicates
        """
        payload = {
            "group": {
                "name": "TechA",
                "code": "TECHA"
            },
            "subgroups": [
                {
                    "name": "Large Cap",
                    "code": "TECHA-LC",
                    "categories": [
                        {
                            "name": "Software",
                            "code": "TECHA-LC-SW",
                            "asset_type": "equity",
                            "assets": [
                                {"symbol": "AAPL123", "name": "Apple123"},
                                {"symbol": "MSFT456", "name": "Microsoft456"}
                            ]
                        }
                    ]
                }
            ]
        }
        
        # First import
        resp1 = self.client.post("/api/import/taxonomy", json=payload)
        assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}: {resp1.json()}"
        stats1 = resp1.json()
        
        # Verify counts on first import
        assert stats1["groups_created"] == 1, f"Expected 1 group created, got {stats1}"
        assert stats1["subgroups_created"] == 1
        assert stats1["categories_created"] == 1
        assert stats1["assets_created"] == 2
        assert stats1["links_created"] == 2
        
        # Second import (same payload)
        resp2 = self.client.post("/api/import/taxonomy", json=payload)
        assert resp2.status_code == 200
        stats2 = resp2.json()
        
        # Verify no new creates, only updates
        assert stats2["groups_created"] == 0
        assert stats2["groups_updated"] == 1
        assert stats2["subgroups_created"] == 0
        assert stats2["subgroups_updated"] == 1
        assert stats2["categories_created"] == 0
        assert stats2["categories_updated"] == 1
        assert stats2["assets_created"] == 0
        assert stats2["assets_updated"] == 2
        assert stats2["links_created"] == 0  # Already exist
        
        # Verify no data duplication in DB
        assets = db_session.query(Asset).filter(Asset.symbol.in_(["AAPL123", "MSFT456"])).all()
        assert len(assets) == 2
    
    def test_import_creates_links(self, db_session):
        """
        Test that import creates CategoryAsset links
        """
        payload = {
            "group": {
                "name": "FinanceB",
                "code": "FINB"
            },
            "subgroups": [
                {
                    "name": "Banks",
                    "code": "FINB-BANK",
                    "categories": [
                        {
                            "name": "US Banks",
                            "code": "FINB-BANK-US",
                            "asset_type": "equity",
                            "assets": [
                                {"symbol": "JPM789", "name": "JPMorgan Chase"},
                                {"symbol": "BAC789", "name": "Bank of America"}
                            ]
                        }
                    ]
                }
            ]
        }
        
        resp = self.client.post("/api/import/taxonomy", json=payload)
        assert resp.status_code == 200
        stats = resp.json()
        
        # Verify creation counts
        assert stats["assets_created"] == 2, f"Expected 2 assets created, got {stats}"
        assert stats["links_created"] == 2
        
        # Verify CategoryAsset links were created
        links = db_session.query(CategoryAsset).all()
        assert len(links) >= 2
        
        # Verify created links have is_candidate=True
        created_symbols = ["JPM789", "BAC789"]
        created_assets = db_session.query(Asset).filter(Asset.symbol.in_(created_symbols)).all()
        for asset in created_assets:
            link = db_session.query(CategoryAsset).filter(CategoryAsset.asset_id == asset.id).first()
            assert link is not None
            assert link.is_candidate is True
    
    def test_import_nested_structure(self, db_session):
        """
        Test complex nested import: multiple subgroups with multiple categories
        """
        payload = {
            "group": {
                "name": "MarketsC",
                "code": "MKTC"
            },
            "subgroups": [
                {
                    "name": "US",
                    "code": "MKTC-US",
                    "categories": [
                        {
                            "name": "Tech",
                            "code": "MKTC-US-TECH",
                            "asset_type": "equity",
                            "assets": [
                                {"symbol": "NVDA001", "name": "NVIDIA"},
                                {"symbol": "AMD001", "name": "Advanced Micro Devices"}
                            ]
                        },
                        {
                            "name": "Energy",
                            "code": "MKTC-US-ENE",
                            "asset_type": "equity",
                            "assets": [
                                {"symbol": "XOM001", "name": "ExxonMobil"}
                            ]
                        }
                    ]
                },
                {
                    "name": "EU",
                    "code": "MKTC-EU",
                    "categories": [
                        {
                            "name": "Auto",
                            "code": "MKTC-EU-AUTO",
                            "asset_type": "equity",
                            "assets": [
                                {"symbol": "BMW001", "name": "BMW"}
                            ]
                        }
                    ]
                }
            ]
        }
        
        resp = self.client.post("/api/import/taxonomy", json=payload)
        assert resp.status_code == 200
        stats = resp.json()
        
        # Verify hierarchical creation
        assert stats["groups_created"] == 1, f"Expected 1 group, got {stats}"
        assert stats["subgroups_created"] == 2, f"Expected 2 subgroups, got {stats}"
        assert stats["categories_created"] == 3, f"Expected 3 categories, got {stats}"
        assert stats["assets_created"] == 4, f"Expected 4 assets, got {stats}"
        assert stats["links_created"] == 4, f"Expected 4 links, got {stats}"
