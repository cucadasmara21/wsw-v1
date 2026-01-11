from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from services import market_data_service


def _fake_bars(n: int):
    base = datetime(2023, 1, 1)
    bars = []
    for i in range(n):
        ts = base + timedelta(minutes=i)
        price = 100 + i
        bars.append({
            "ts": ts.isoformat(),
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 1000 + i,
            "source": "test",
        })
    return bars


def test_market_bars_success(client: TestClient, monkeypatch):
    fake_bars = _fake_bars(30)
    monkeypatch.setattr(market_data_service, "get_bars", lambda *args, **kwargs: fake_bars)

    response = client.get("/api/market/bars?symbol=TSLA&interval=1d&limit=30")
    assert response.status_code == 200

    data = response.json()
    assert data["count"] == 30
    assert data["symbol"] == "TSLA"
    assert isinstance(data["bars"], list)
    assert data["bars"][0]["close"] == fake_bars[0]["close"]


def test_snapshot_success(client: TestClient, monkeypatch):
    fake_bars = _fake_bars(40)
    monkeypatch.setattr(market_data_service, "get_bars", lambda *args, **kwargs: fake_bars)

    response = client.get("/api/market/snapshot?symbol=TSLA&interval=1d&limit=40&persist=false")
    assert response.status_code == 200

    data = response.json()
    assert data["symbol"] == "TSLA"
    assert 0 <= data["risk"]["score_total_0_100"] <= 100
    assert data["indicators"]["sma20"] is not None
    assert data["indicators"]["rsi14"] is not None


def test_snapshot_insufficient_data(client: TestClient, monkeypatch):
    fake_bars = _fake_bars(5)
    monkeypatch.setattr(market_data_service, "get_bars", lambda *args, **kwargs: fake_bars)

    response = client.get("/api/market/snapshot?symbol=TSLA&interval=1d&limit=20&persist=false")
    assert response.status_code == 422

    payload = response.json()
    error = payload.get("error") or {}
    assert error.get("code") == 422
    assert "Not enough data" in error.get("message", "")
