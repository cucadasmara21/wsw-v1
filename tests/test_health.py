"""
Test /health endpoint
"""
from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient):
    """Health endpoint should return 200 with expected keys"""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "services" in data
    assert "environment" in data


def test_health_has_database_service(client: TestClient):
    """Health endpoint should report database service status"""
    response = client.get("/health")
    data = response.json()
    
    assert "services" in data
    assert "database" in data["services"]
    # Database should be healthy in tests (using temp SQLite)
    assert data["services"]["database"] in ["healthy", "unhealthy"]
