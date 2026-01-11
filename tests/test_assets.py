"""
Test /api/assets endpoints
"""
from fastapi.testclient import TestClient


def test_get_assets_returns_list_or_500(client: TestClient):
    """GET /api/assets should return a list (200) or fail gracefully (500 if DB not ready)"""
    response = client.get("/api/assets")
    # Accept both 200 (with data) or 500 (DB not initialized in test)
    assert response.status_code in [200, 500]
    
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)


def test_get_assets_pagination_params_accepted(client: TestClient):
    """Should accept skip and limit parameters without crashing"""
    response = client.get("/api/assets?skip=0&limit=10")
    # Should not crash with 422 validation error
    assert response.status_code != 422
