from __future__ import annotations

import logging
import json
import os
import time
from typing import Optional
from pathlib import Path
from urllib import request as _urllib_request

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError

from config import redact_database_url, settings
from database import engine, get_db
from services.vertex28 import VERTEX28_STRIDE

# Route A: Vertex28 only (no legacy).
from api.universe_v8 import get_v8_status

logger = logging.getLogger(__name__)
router = APIRouter()

_DEBUG_LOG_PATH = r"c:\Users\alber\Documents\wsw-v1\.cursor\debug.log"
_DEBUG_INGEST_URL = "http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a"


def _dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        # Attempt primary (system-provided) path; fall back to repo-local path if needed.
        primary = _DEBUG_LOG_PATH
        try:
            os.makedirs(os.path.dirname(primary), exist_ok=True)
            target = primary
        except Exception:
            repo_root = Path(__file__).resolve().parents[1]
            target = str(repo_root / ".cursor" / "debug.log")
            os.makedirs(os.path.dirname(target), exist_ok=True)

        payload = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(target, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    try:
        # If the backend runs in a container, file logging may not land in the workspace.
        # Also emit to the session ingest server (best-effort).
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = _urllib_request.Request(
            _DEBUG_INGEST_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        _urllib_request.urlopen(req, timeout=0.2).read()  # noqa: S310
    except Exception:
        pass
    # endregion agent log


def _remediation() -> str:
    return (
        "Route A requires PostgreSQL + seeded universe_assets.\n"
        "Windows PowerShell:\n"
        '  $env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/wsw_db"\n'
        '  $env:DATABASE_DSN_ASYNC="postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"\n'
        "Seed (Route A):\n"
        "  python .\\backend\\scripts\\seed_universe_v8.py --target 5000 --verify\n"
    )


@router.get("/tree")
def universe_tree() -> dict:
    """
    Route A: /api/universe/tree (Postgres-only).

    Validation:
      curl.exe -i http://127.0.0.1:8000/api/universe/tree
    """
    q_source = text(
        """
        SELECT
          COALESCE(NULLIF(btrim(sector), ''), 'UNKNOWN') AS grp,
          CASE
            WHEN upper(left(COALESCE(NULLIF(btrim(symbol), ''), 'Z'), 1)) BETWEEN 'A' AND 'M' THEN 'A-M'
            ELSE 'N-Z'
          END AS subgrp,
          COUNT(*)::int AS cnt
        FROM public.source_assets
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    )
    q_universe = text(
        """
        SELECT
          COALESCE(NULLIF(btrim(sector), ''), 'UNKNOWN') AS grp,
          CASE
            WHEN upper(left(COALESCE(NULLIF(btrim(symbol), ''), 'Z'), 1)) BETWEEN 'A' AND 'M' THEN 'A-M'
            ELSE 'N-Z'
          END AS subgrp,
          COUNT(*)::int AS cnt
        FROM public.universe_assets
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
    )

    try:
        with engine.connect() as conn:
            used = "public.source_assets"
            try:
                rows = conn.execute(q_source).mappings().all()
            except ProgrammingError as e:
                # Allow fallback only when the source table/view isn't available yet.
                used = "public.universe_assets"
                _dbg(
                    "H2",
                    "api/universe.py:universe_tree",
                    "fallback_to_universe_assets",
                    {"error": f"{type(e).__name__}: {str(e)[:200]}"},
                )
                rows = conn.execute(q_universe).mappings().all()
            except Exception as e:
                # Do not silently hide programming/runtime errors.
                _dbg(
                    "H2",
                    "api/universe.py:universe_tree",
                    "tree_query_failed_source_assets",
                    {"error": f"{type(e).__name__}: {str(e)[:200]}"},
                )
                raise
    except Exception as e:
        logger.exception("Route A /api/universe/tree failed: %s", e)
        _dbg(
            "H2",
            "api/universe.py:universe_tree",
            "tree_endpoint_500",
            {"error": f"{type(e).__name__}: {str(e)[:200]}"},
        )
        raise HTTPException(status_code=500, detail=f"Route A tree query failed: {type(e).__name__}: {e}")

    _dbg(
        "H2",
        "api/universe.py:universe_tree",
        "tree_endpoint_200",
        {"used": used, "rows": len(rows)},
    )

    if not rows:
        return {"groups": []}

    groups: dict[str, dict] = {}
    for r in rows:
        g = str(r["grp"])
        sg = str(r["subgrp"])
        cnt = int(r["cnt"] or 0)
        if g not in groups:
            groups[g] = {"name": g, "count": 0, "subgroups": []}
        groups[g]["count"] += cnt
        groups[g]["subgroups"].append({"name": sg, "count": cnt})

    return {"groups": list(groups.values())}


@router.get("/points.bin")
def points_bin(
    db: Session = Depends(get_db),
    limit: int = Query(2000, ge=1, le=1_000_000),
) -> Response:
    # Route A: legacy endpoint removed. Use the V8 snapshot contract.
    raise HTTPException(
        status_code=410,
        detail={
            "code": 410,
            "message": "Route A: /api/universe/points.bin is removed. Use /api/universe/v8/snapshot?format=vertex28.",
            "database_url_redacted": redact_database_url(settings.DATABASE_URL or ""),
            "remediation": _remediation(),
        },
    )
