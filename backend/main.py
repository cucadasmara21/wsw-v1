from __future__ import annotations

"""
Route A backend entrypoint wrapper.

This exists to satisfy tooling expecting `backend.main`.
The canonical FastAPI app lives in repo-root `main.py`.
"""

from main import app  # noqa: F401

