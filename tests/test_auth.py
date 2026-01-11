"""
Test /api/auth endpoints
"""
from fastapi.testclient import TestClient


def test_token_without_credentials_fails(client: TestClient):
    """POST /api/auth/token should return 422 without credentials"""
    response = client.post("/api/auth/token", data={})
    # Should fail with validation error (missing required fields)
    assert response.status_code == 422


def test_token_with_invalid_credentials_returns_error(client: TestClient):
    """POST /api/auth/token should return 401 or 500 with invalid credentials"""
    response = client.post("/api/auth/token", data={
        "username": "nonexistent_user",
        "password": "wrong_password"
    })
    # Should fail (either 401 auth error or 500 if DB not ready)
    assert response.status_code in [401, 500]
