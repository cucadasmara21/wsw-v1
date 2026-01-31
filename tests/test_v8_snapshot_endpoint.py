from __future__ import annotations

from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.vertex28 import pack_vertex28


class _FakeResult:
    def __init__(self, *, scalar_value=None, all_rows=None):
        self._scalar_value = scalar_value
        self._all_rows = all_rows or []

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self

    def all(self):
        return self._all_rows


class _FakeConn:
    def __init__(self, *, has_mv: bool, has_table: bool, rows: list[tuple[object]]):
        self._has_mv = has_mv
        self._has_table = has_table
        self._rows = rows

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if "SELECT 1" in sql:
            return _FakeResult(scalar_value=1)
        if "to_regclass('public.universe_snapshot_v8')" in sql:
            return _FakeResult(scalar_value=self._has_mv)
        if "to_regclass('public.assets')" in sql:
            return _FakeResult(scalar_value=False)
        if "to_regclass('public.universe_assets')" in sql:
            return _FakeResult(scalar_value=self._has_table)
        if "SELECT COUNT(*) FROM public.universe_assets" in sql:
            return _FakeResult(scalar_value=len(self._rows))
        if "octet_length(vertex_buffer)" in sql:
            # stride check: 0 bad rows
            return _FakeResult(scalar_value=0)
        if "SELECT vertex_buffer" in sql:
            return _FakeResult(all_rows=self._rows)
        return _FakeResult()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@contextmanager
def _fake_connect(conn: _FakeConn):
    yield conn


def test_snapshot_returns_503_when_objects_missing(monkeypatch):
    from api import universe_v8 as mod

    # Force Postgres gate to pass for unit test (we're mocking the DB layer anyway).
    monkeypatch.setattr(mod.settings, "DATABASE_URL", "postgresql://localhost/wsw_db", raising=False)

    fake = _FakeConn(has_mv=False, has_table=False, rows=[])
    monkeypatch.setattr(mod.engine, "connect", lambda: _fake_connect(fake))

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    r = client.get("/api/universe/v8/snapshot?format=vertex28&compression=none&limit=10")
    assert r.status_code == 503
    assert "remediation" in r.json()["detail"]


def test_snapshot_returns_vertex28_bytes(monkeypatch):
    from api import universe_v8 as mod

    monkeypatch.setattr(mod.settings, "DATABASE_URL", "postgresql://localhost/wsw_db", raising=False)

    rec = pack_vertex28(1, 2, 0.1, 0.2, 0.3, 0.9, 0.5)
    # Simulate psycopg2 BYTEA behavior (memoryview)
    rows = [(memoryview(rec),) for _ in range(10)]
    fake = _FakeConn(has_mv=True, has_table=True, rows=rows)
    monkeypatch.setattr(mod.engine, "connect", lambda: _fake_connect(fake))

    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app)

    r = client.get("/api/universe/v8/snapshot?format=vertex28&compression=none&limit=10")
    assert r.status_code == 200
    assert len(r.content) == 28 * 10
    assert (len(r.content) % 28) == 0
