from __future__ import annotations

"""
Route A configuration wrapper (PostgreSQL-only, fail-fast).

Validation snippet:
  powershell -command "$env:DATABASE_URL='sqlite:///./wsw.db'; python -c \"import backend.config\""
  # must raise RuntimeError
"""

# Importing root `config` must fail-fast when DATABASE_URL is missing/invalid (e.g., sqlite).
from config import settings, parse_db_scheme, redact_database_url  # noqa: F401

