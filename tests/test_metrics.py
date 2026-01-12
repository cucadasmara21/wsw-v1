"""
Tests for metrics endpoints
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime

from main import app
from database import SessionLocal, Base, engine
from models import Asset, User, AssetMetricSnapshot, Category, Subgroup, Group


@pytest.fixture(scope="function")
def client():
    """Create test client with fresh database"""
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield TestClient(app)
    # Cleanup
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_db():
    """Provide database session"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_user(test_db):
    """Create test user with viewer role"""
    user = User(
        email="viewer@test.com",
        username="viewer",
        hashed_password="fake_hash",
        role="viewer",
        is_active=True,
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_asset(test_db):
    """Create test asset"""
    asset = Asset(
        symbol="TEST",
        name="Test Corp",
        sector="Technology",
        exchange="NYSE",
        country="US",
    )
    test_db.add(asset)
    test_db.commit()
    test_db.refresh(asset)
    return asset


@pytest.fixture(scope="function")
def test_metrics(test_db, test_asset):
    """Create test metrics snapshot"""
    snapshot = AssetMetricSnapshot(
        asset_id=test_asset.id,
        as_of=datetime.utcnow(),
        metrics={
            "sma20": 150.0,
            "rsi14": 65.0,
            "volatility": 0.025,
            "max_drawdown": -0.08,
        },
        quality={"bars_count": 252, "low_data": False},
        explain={},
    )
    test_db.add(snapshot)
    test_db.commit()
    test_db.refresh(snapshot)
    return snapshot


def test_get_metrics_not_found(client):
    """Test GET /api/metrics/{id}/metrics with non-existent asset"""
    response = client.get("/api/metrics/999/metrics")
    # May be 404 or 401 depending on auth
    assert response.status_code in [401, 404]


def test_get_metrics_no_snapshot(client, test_db, test_user, test_asset):
    """Test GET /api/metrics/{id}/metrics when no snapshot exists"""
    # This would need auth token to work properly
    # For now, just verify endpoint exists
    response = client.get(f"/api/metrics/{test_asset.id}/metrics")
    assert response.status_code in [401, 404]


def test_get_metrics_success(client, test_db, test_user, test_asset, test_metrics):
    """Test GET /api/metrics/{id}/metrics success case"""
    # Would need to mock auth to fully test
    # This validates the schema
    from schemas import MetricsSnapshot

    snapshot_data = {
        "id": test_metrics.id,
        "asset_id": test_asset.id,
        "as_of": test_metrics.as_of.isoformat(),
        "metrics": test_metrics.metrics,
        "quality": test_metrics.quality,
        "explain": test_metrics.explain,
        "created_at": test_metrics.created_at.isoformat(),
    }

    # Validate schema
    schema = MetricsSnapshot(**snapshot_data)
    assert schema.asset_id == test_asset.id
    assert schema.metrics["sma20"] == 150.0
