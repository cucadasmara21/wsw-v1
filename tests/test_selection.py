"""
Tests for selection API and service
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from models import Category, Asset, Price, CategoryAsset, Subgroup, Group
from services import selection_service


@pytest.fixture
def seed_category_data(client):
    """Seed minimal category + assets + prices for testing"""
    from database import SessionLocal
    
    db = SessionLocal()
    try:
        # Create group -> subgroup -> category (without explicit IDs)
        group = Group(name="Test Selection Group")
        db.add(group)
        db.flush()
        
        subgroup = Subgroup(group_id=group.id, name="Test Selection Subgroup")
        db.add(subgroup)
        db.flush()
        
        category = Category(subgroup_id=subgroup.id, name="Test Selection Category")
        db.add(category)
        db.flush()
        
        # Create 3 test assets
        assets = [
            Asset(symbol="TSTSEL1", name="Test Asset 1", category_id=category.id),
            Asset(symbol="TSTSEL2", name="Test Asset 2", category_id=category.id),
            Asset(symbol="TSTSEL3", name="Test Asset 3", category_id=category.id),
        ]
        for asset in assets:
            db.add(asset)
        db.flush()
        
        asset_ids = [a.id for a in assets]
        
        # Create CategoryAsset candidates
        for asset in assets:
            ca = CategoryAsset(
                category_id=category.id,
                asset_id=asset.id,
                is_candidate=True,
                is_selected=False
            )
            db.add(ca)
        
        # Add price history (90 days)
        base_date = datetime.utcnow() - timedelta(days=90)
        
        # Asset 1: Stable, low vol
        for i in range(90):
            price = Price(
                time=base_date + timedelta(days=i),
                asset_id=asset_ids[0],
                close=100.0 + i * 0.1,  # Slow uptrend
                volume=500_000
            )
            db.add(price)
        
        # Asset 2: High vol, higher returns
        for i in range(90):
            price = Price(
                time=base_date + timedelta(days=i),
                asset_id=asset_ids[1],
                close=100.0 + i * 0.5,  # Faster uptrend
                volume=2_000_000  # Higher liquidity
            )
            db.add(price)
        
        # Asset 3: Minimal data (should score lower)
        for i in range(15):  # Only 15 days
            price = Price(
                time=base_date + timedelta(days=i),
                asset_id=asset_ids[2],
                close=100.0,
                volume=100_000
            )
            db.add(price)
        
        db.commit()
        
        result = {
            "category_id": category.id,
            "group_id": group.id,
            "subgroup_id": subgroup.id,
            "asset_ids": asset_ids
        }
        
        yield result
        
    finally:
        # Cleanup - order matters due to foreign keys
        try:
            if 'asset_ids' in result:
                db.query(Price).filter(Price.asset_id.in_(result["asset_ids"])).delete(synchronize_session=False)
                db.query(CategoryAsset).filter(CategoryAsset.asset_id.in_(result["asset_ids"])).delete(synchronize_session=False)
                db.query(Asset).filter(Asset.id.in_(result["asset_ids"])).delete(synchronize_session=False)
            if 'category_id' in result:
                db.query(Category).filter(Category.id == result["category_id"]).delete(synchronize_session=False)
            if 'subgroup_id' in result:
                db.query(Subgroup).filter(Subgroup.id == result["subgroup_id"]).delete(synchronize_session=False)
            if 'group_id' in result:
                db.query(Group).filter(Group.id == result["group_id"]).delete(synchronize_session=False)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Cleanup error: {e}")
        finally:
            db.close()


def test_selection_preview_returns_top_n(client, seed_category_data):
    """Test preview endpoint returns correct number of selected assets"""
    category_id = seed_category_data["category_id"]
    
    response = client.get(f"/api/selection/categories/{category_id}/preview?top_n=2&lookback_days=30")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "selected" in data
    assert "candidates" in data
    assert "meta" in data
    
    # Should return top 2
    assert len(data["selected"]) == 2
    
    # Should have ranks assigned
    assert data["selected"][0]["rank"] == 1
    assert data["selected"][1]["rank"] == 2
    
    # Should have explain dicts
    assert "explain" in data["selected"][0]
    assert "total" in data["selected"][0]["explain"]
    
    # Meta should match request
    assert data["meta"]["top_n"] == 2
    assert data["meta"]["lookback_days"] == 30
    assert data["meta"]["category_id"] == category_id


def test_selection_recompute_persists_and_updates_flags(client, seed_category_data, monkeypatch):
    """Test recompute endpoint persists SelectionRun and updates CategoryAsset flags"""
    from database import SessionLocal
    from models import SelectionRun
    
    category_id = seed_category_data["category_id"]
    
    # Mock market_data_service to avoid external calls
    from services import market_data_service
    
    def mock_get_snapshot(symbol):
        return {
            "price": 100.0,
            "source": "mock",
            "cached": False,
            "stale": False,
            "confidence": 1.0
        }
    
    monkeypatch.setattr(market_data_service, "get_snapshot", mock_get_snapshot)
    
    # Execute recompute
    response = client.post(f"/api/selection/categories/{category_id}/recompute?top_n=2&lookback_days=30")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["selected"]) == 2
    
    # Verify SelectionRun was created
    db = SessionLocal()
    try:
        run = db.query(SelectionRun).filter(SelectionRun.category_id == category_id).first()
        assert run is not None
        assert run.top_n == 2
        assert run.lookback_days == 30
        assert "selected" in run.results_json
        
        # Verify CategoryAsset flags updated
        selected_ca = (
            db.query(CategoryAsset)
            .filter(CategoryAsset.category_id == category_id, CategoryAsset.is_selected == True)
            .all()
        )
        
        # Should have 2 selected
        assert len(selected_ca) == 2
        
        # Should have scores and ranks
        for ca in selected_ca:
            assert ca.last_score is not None
            assert ca.score_ema is not None
            assert ca.last_rank is not None
            assert ca.last_rank <= 2
    
    finally:
        db.close()


def test_selection_preview_handles_no_candidates(client):
    """Test preview returns empty when category has no candidates"""
    from database import SessionLocal
    
    db = SessionLocal()
    try:
        # Create empty category
        group = Group(name="Empty Selection Group")
        db.add(group)
        db.flush()
        
        subgroup = Subgroup(group_id=group.id, name="Empty Selection Subgroup")
        db.add(subgroup)
        db.flush()
        
        category = Category(subgroup_id=subgroup.id, name="Empty Selection Category")
        db.add(category)
        db.commit()
        
        category_id = category.id
        group_id = group.id
        subgroup_id = subgroup.id
        
        response = client.get(f"/api/selection/categories/{category_id}/preview?top_n=10")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["selected"] == []
        assert data["candidates"] == []
        assert "no_candidates" in str(data["meta"])
        
    finally:
        db.query(Category).filter(Category.id == category_id).delete(synchronize_session=False)
        db.query(Subgroup).filter(Subgroup.id == subgroup_id).delete(synchronize_session=False)
        db.query(Group).filter(Group.id == group_id).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_selection_current_returns_persisted_flags(client, seed_category_data, monkeypatch):
    """Test current endpoint returns persisted selection without recalculation"""
    from database import SessionLocal
    from services import market_data_service
    
    category_id = seed_category_data["category_id"]
    
    def mock_get_snapshot(symbol):
        return {"price": 100.0, "source": "mock", "cached": False, "stale": False, "confidence": 1.0}
    
    monkeypatch.setattr(market_data_service, "get_snapshot", mock_get_snapshot)
    
    # First recompute to set persisted state
    client.post(f"/api/selection/categories/{category_id}/recompute?top_n=2")
    
    # Then get current
    response = client.get(f"/api/selection/categories/{category_id}/current?top_n=2")
    
    assert response.status_code == 200
    data = response.json()
    
    assert "selected" in data
    assert len(data["selected"]) == 2
    assert data["meta"]["source"] == "persisted_flags"
    
    # Should have persisted fields
    for item in data["selected"]:
        assert "score_ema" in item
        assert "last_selected_at" in item
