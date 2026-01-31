from __future__ import annotations

"""
Route A database wrapper (PostgreSQL-only, fail-fast).

This module re-exports the canonical engine/session from repo-root `database.py`.
No SQLite fallbacks are permitted under Route A.

Validation snippet:
  powershell -command "$env:DATABASE_URL='sqlite:///./wsw.db'; python -c \"import backend.database\""
  # must raise RuntimeError at import time
"""

from database import (  # noqa: F401
    Base,
    SessionLocal,
    engine,
    get_db,
    init_database,
    test_connections,
    ensure_v8_schema,
)

