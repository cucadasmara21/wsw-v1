"""
Tests for alerts endpoints
"""
import pytest
from datetime import datetime

from database import SessionLocal, Base, engine
from models import Asset, User, Alert


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
    """Create test user"""
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
def test_alert(test_db, test_asset):
    """Create test alert"""
    alert = Alert(
        asset_id=test_asset.id,
        key="rsi_high",
        severity="warning",
        message="RSI14 is high (75.2)",
        triggered_at=datetime.utcnow(),
        payload={"rsi": 75.2},
    )
    test_db.add(alert)
    test_db.commit()
    test_db.refresh(alert)
    return alert


def test_alert_model_creation(test_db, test_asset):
    """Test Alert model creation"""
    alert = Alert(
        asset_id=test_asset.id,
        key="drawdown_alert",
        severity="critical",
        message="Large drawdown (-15%)",
        triggered_at=datetime.utcnow(),
        payload={"drawdown": -0.15},
    )
    test_db.add(alert)
    test_db.commit()
    test_db.refresh(alert)

    assert alert.id is not None
    assert alert.key == "drawdown_alert"
    assert alert.severity == "critical"
    assert alert.resolved_at is None


def test_alert_resolve(test_db, test_alert):
    """Test marking an alert as resolved"""
    assert test_alert.resolved_at is None

    test_alert.resolved_at = datetime.utcnow()
    test_db.commit()
    test_db.refresh(test_alert)

    assert test_alert.resolved_at is not None


def test_alert_query_active(test_db, test_asset):
    """Test querying only active (unresolved) alerts"""
    # Create 2 active alerts
    for i in range(2):
        alert = Alert(
            asset_id=test_asset.id,
            key=f"alert_{i}",
            severity="warning",
            message=f"Alert {i}",
            triggered_at=datetime.utcnow(),
            payload={},
        )
        test_db.add(alert)

    # Create 1 resolved alert
    resolved = Alert(
        asset_id=test_asset.id,
        key="resolved_alert",
        severity="info",
        message="Resolved",
        triggered_at=datetime.utcnow(),
        resolved_at=datetime.utcnow(),
        payload={},
    )
    test_db.add(resolved)
    test_db.commit()

    # Query active only
    active_alerts = test_db.query(Alert).filter(Alert.resolved_at == None).all()
    assert len(active_alerts) == 2


def test_alert_query_by_severity(test_db, test_asset):
    """Test querying alerts by severity"""
    # Create alerts with different severities
    severities = ["info", "warning", "critical"]
    for sev in severities:
        alert = Alert(
            asset_id=test_asset.id,
            key=f"alert_{sev}",
            severity=sev,
            message=f"{sev} alert",
            triggered_at=datetime.utcnow(),
            payload={},
        )
        test_db.add(alert)
    test_db.commit()

    # Query critical only
    critical = test_db.query(Alert).filter(Alert.severity == "critical").all()
    assert len(critical) == 1
    assert critical[0].severity == "critical"


def test_alert_schema_validation():
    """Test AlertOut schema validation"""
    from schemas import AlertOut

    alert_data = {
        "id": 1,
        "asset_id": 100,
        "key": "test_alert",
        "severity": "warning",
        "message": "Test message",
        "triggered_at": datetime.utcnow(),
        "resolved_at": None,
        "payload": {"data": "value"},
    }

    schema = AlertOut(**alert_data)
    assert schema.asset_id == 100
    assert schema.severity == "warning"
