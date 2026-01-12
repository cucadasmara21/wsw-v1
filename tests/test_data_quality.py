from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from services import market_data_service
from services.rate_limiter import rate_limiter


def _fake_bars(n: int):
    base = datetime(2024, 1, 1)
    bars = []
    for i in range(n):
        ts = base + timedelta(days=i)
        price = 100 + i
        bars.append({
            "ts": ts,
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": 1000 + i,
            "source": "test",
        })
    return bars


def test_health_includes_data_quality(client: TestClient):
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    dq = body.get("data_quality") or {}
    assert {"cached_percent", "stale_percent", "avg_confidence", "provider_errors", "rate_limited"} <= set(dq.keys())
    assert 0 <= float(dq.get("cached_percent", 0)) <= 100
    assert 0 <= float(dq.get("stale_percent", 0)) <= 100
    assert float(dq.get("avg_confidence", 0)) >= 0
    assert int(dq.get("provider_errors", 0)) >= 0
    assert int(dq.get("rate_limited", 0)) >= 0


def test_snapshot_cache_counts_in_health(client: TestClient, monkeypatch):
    # Ensure provider path returns deterministic fake bars
    fake = _fake_bars(40)
    monkeypatch.setattr(market_data_service, "YFINANCE_AVAILABLE", True)
    monkeypatch.setattr(market_data_service, "fetch_history", lambda *args, **kwargs: fake)

    # First call (provider)
    res1 = client.get("/api/market/snapshot?symbol=TSLA&interval=1d&limit=40&persist=false")
    assert res1.status_code == 200

    # Second call should hit cache path and increase cache_hits
    res2 = client.get("/api/market/snapshot?symbol=TSLA&interval=1d&limit=40&persist=false")
    assert res2.status_code == 200

    # Check health cached_percent > 0
    h = client.get("/health")
    assert h.status_code == 200
    dq = (h.json().get("data_quality") or {})
    assert float(dq.get("cached_percent", 0)) > 0


def test_rate_limit_increments_health(client: TestClient, monkeypatch):
    # Force rate limiter to deny
    monkeypatch.setattr(rate_limiter, "is_allowed", lambda ip: False)

    res = client.get("/api/market/snapshot?symbol=TSLA&interval=1d&limit=40&persist=false")
    assert res.status_code == 429

    # Verify rate_limited counter incremented
    h = client.get("/health")
    dq = (h.json().get("data_quality") or {})
    assert int(dq.get("rate_limited", 0)) >= 1
