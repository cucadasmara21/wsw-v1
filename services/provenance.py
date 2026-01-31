"""
Minimal provenance support for Route A ingestion.
When ENABLE_PROVENANCE=true, ingestion_run_id/source/observed_at/row_digest
are populated for tamper detection.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def compute_row_digest(columns: dict[str, Any], *, exclude: frozenset[str] | None = None) -> str:
    """
    SHA256 digest over canonical JSON of selected columns for tamper detection.
    exclude: column names to omit from digest (e.g. vertex_buffer, row_digest).
    """
    exc = exclude or frozenset()
    payload = {k: v for k, v in sorted(columns.items()) if k not in exc}
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
