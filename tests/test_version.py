"""
Test /version endpoint
"""
from fastapi.testclient import TestClient


def test_version_returns_200(client: TestClient):
    """Version endpoint should return 200 with required fields"""
    response = client.get("/version")
    assert response.status_code == 200
    
    data = response.json()
    # These fields must exist (can be null/empty but must be present)
    assert "app" in data
    assert "version" in data
    assert "git_sha" in data
    assert "build_time" in data
    assert "environment" in data
    assert "debug" in data


def test_version_git_sha_is_string(client: TestClient):
    """git_sha should be a string (even if empty)"""
    response = client.get("/version")
    data = response.json()
    
    assert isinstance(data["git_sha"], str)
    # Can be empty in test environment, that's OK


def test_version_has_app_name(client: TestClient):
    """App name should be present"""
    response = client.get("/version")
    data = response.json()
    
    assert data["app"] is not None
    assert isinstance(data["app"], str)
    assert len(data["app"]) > 0
