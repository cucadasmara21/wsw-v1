from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_version_has_fields():
    res = client.get("/version")
    assert res.status_code == 200
    data = res.json()
    assert "git_sha" in data
    assert "build_time" in data
    assert isinstance(data["git_sha"], str)
