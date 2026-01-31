from __future__ import annotations

import logging
import struct
import time
import uuid
from typing import Optional

import asyncio
import json
import os
from pathlib import Path
from urllib import request as _urllib_request

from fastapi import APIRouter, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from config import parse_db_scheme, redact_database_url, settings
from database import engine
from services.vertex28 import VERTEX28_STRIDE
from services.vertex28 import pack_vertex28
from services.vertex28 import validate_vertex28_blob

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/universe/v8", tags=["quantum"])

_DEBUG_LOG_PATH = r"c:\Users\alber\Documents\wsw-v1\.cursor\debug.log"
_DEBUG_INGEST_URL = "http://127.0.0.1:7242/ingest/2c312865-94f7-427e-905b-dc7584b4541a"


def _dbg(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
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
        "Set DATABASE_URL to PostgreSQL (TITAN V8 requires Postgres).\n"
        "Windows PowerShell:\n"
        '  $env:DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/wsw_db"\n'
        '  $env:DATABASE_DSN_ASYNC="postgresql://postgres:postgres@localhost:5432/wsw_db"\n'
        "Docker compose:\n"
        "  docker compose up -d\n"
    )


def _require_postgres() -> str:
    dsn = settings.DATABASE_URL or ""
    scheme = parse_db_scheme(dsn)
    if scheme != "postgresql":
        raise HTTPException(
            status_code=503,
            detail={
                "code": 503,
                "message": "Titan V8 requires PostgreSQL. DATABASE_URL must be a PostgreSQL connection string.",
                "detected_scheme": scheme,
                "effective_database_url_redacted": redact_database_url(dsn),
                "remediation": _remediation(),
                "request_id": str(uuid.uuid4()),
            },
        )
    return dsn


VERTEX28_LAYOUT = "<IIfffff"
_V28 = struct.Struct(VERTEX28_LAYOUT)
assert _V28.size == VERTEX28_STRIDE


@router.get("/health")
@router.head("/health")
async def v8_health(request: Request):
    s = get_v8_status()
    v8_ready = bool(s["ready"])
    reason: Optional[str] = s.get("reason")

    if request.method == "HEAD":
        # Route A: 200 only when PostgreSQL is active AND seeded AND contract-ok.
        return Response(status_code=200 if v8_ready else 503)

    payload = {
        "status": "healthy" if v8_ready else "unavailable",
        "v8_ready": bool(v8_ready),
        "database_url_scheme": s["database_url_scheme"],
        "effective_database_url_redacted": redact_database_url(settings.DATABASE_URL or ""),
        "database_url_effective": redact_database_url(settings.DATABASE_URL or ""),
        "db_ok": bool(s["db_ok"]),
        "schema_ok": bool(s["schema_ok"]),
        "rows": int(s["rows"]),
        "ready": bool(s["ready"]),
        "vertex_stride": int(s.get("vertex_stride") or VERTEX28_STRIDE),
        "format": str(s.get("format") or "vertex28"),
        "stride_ok": bool(s.get("stride_ok")),
        "reason": reason,
        "remediation": None if v8_ready else _remediation(),
    }
    return JSONResponse(content=payload, status_code=200 if v8_ready else 503)


def _snapshot_prereq_remediation() -> str:
    return (
        "Prerequisites missing for TITAN V8 snapshot.\n"
        "1) Ensure schema exists and data is seeded.\n"
        "   - Run seeder: python .\\backend\\scripts\\seed_universe_v8.py --target 200000\n"
        "2) (Optional) Create MV for faster snapshots:\n"
        "   CREATE MATERIALIZED VIEW public.universe_snapshot_v8 AS\n"
        "     SELECT morton_code, vertex_buffer FROM public.universe_assets;\n"
        "   CREATE INDEX idx_universe_snapshot_v8_morton ON public.universe_snapshot_v8(morton_code);\n"
        "   REFRESH MATERIALIZED VIEW public.universe_snapshot_v8;\n"
    )


def _engine_diag() -> dict:
    try:
        dialect = engine.dialect.name
        driver = getattr(engine.dialect, "driver", "unknown")
    except Exception:
        dialect = "unknown"
        driver = "unknown"
    return {
        "dialect": dialect,
        "driver": driver,
        "db_scheme": parse_db_scheme(settings.DATABASE_URL or ""),
        "database_url_redacted": redact_database_url(settings.DATABASE_URL or ""),
    }


def _ensure_v8_schema_best_effort() -> None:
    """
    Ensure canonical V8 relation exists (Postgres only).
    This calls the shared DB bootstrap, in an isolated transaction scope.
    """
    try:
        from database import ensure_v8_schema

        ensure_v8_schema()
    except Exception as e:
        logger.debug("[V8] could not ensure V8 schema: %s: %s", type(e).__name__, e)


def get_v8_status() -> dict:
    """
    Source-of-truth V8 readiness for both /health and /snapshot.

    Route A: ready = db_ok AND schema_ok AND rows > 0 AND Vertex28 stride OK AND MV exists.
    """
    dsn = settings.DATABASE_URL or ""
    scheme = parse_db_scheme(dsn)
    diag = _engine_diag()
    status = {
        "database_url_scheme": scheme,
        "db_ok": False,
        "schema_ok": False,
        "rows": 0,
        "ready": False,
        "reason": None,
        "vertex_stride": VERTEX28_STRIDE,
        "format": "vertex28",
        "stride_ok": False,
        "assets_view_exists": False,
        "mv_exists": False,
        "diagnostics": diag,
    }
    if scheme != "postgresql":
        status["reason"] = "DATABASE_URL is not PostgreSQL; V8 requires Postgres"
        return status

    # Route A: best-effort schema bootstrap (idempotent) so health can report accurate state.
    _ensure_v8_schema_best_effort()

    rel = "public.universe_assets"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            status["db_ok"] = True

            try:
                status["assets_view_exists"] = bool(conn.execute(text("SELECT to_regclass('public.assets') IS NOT NULL")).scalar())
            except Exception:
                status["assets_view_exists"] = False

            try:
                status["mv_exists"] = bool(
                    conn.execute(text("SELECT to_regclass('public.universe_snapshot_v8') IS NOT NULL")).scalar()
                )
            except Exception:
                status["mv_exists"] = False

            has_table = bool(conn.execute(text("SELECT to_regclass('public.universe_assets') IS NOT NULL")).scalar())
            # Route A: schema_ok = required canonical table exists.
            # MV existence is tracked separately and required for snapshot readiness.
            status["schema_ok"] = bool(has_table)
            if not has_table:
                status["reason"] = f"Missing required table {rel}"
                status["ready"] = False
                return status
            try:
                status["rows"] = int(conn.execute(text("SELECT COUNT(*) FROM public.universe_assets")).scalar() or 0)
            except Exception:
                status["rows"] = 0

            try:
                bad_stride = int(
                    conn.execute(
                        text(
                            "SELECT COUNT(*) FROM public.universe_assets "
                            "WHERE vertex_buffer IS NULL OR octet_length(vertex_buffer) != :s"
                        ),
                        {"s": int(VERTEX28_STRIDE)},
                    ).scalar()
                    or 0
                )
            except Exception:
                bad_stride = 1
            status["stride_ok"] = bool(bad_stride == 0 and status["rows"] > 0)

            # Route A gate: require at least 1 row.
            if status["rows"] <= 0:
                status["ready"] = False
                status["reason"] = "universe_assets empty; run seeding/materialization"
                return status
            if not status["mv_exists"]:
                status["ready"] = False
                status["reason"] = "Missing required materialized view public.universe_snapshot_v8"
                return status
            if not status["stride_ok"]:
                status["ready"] = False
                status["reason"] = "vertex_buffer missing or stride != 28; re-run Route A seeder"
                return status

            status["ready"] = True
            status["reason"] = None
            return status
    except Exception as e:
        status["db_ok"] = False
        status["schema_ok"] = False
        status["ready"] = False
        status["reason"] = f"PostgreSQL unreachable: {type(e).__name__}: {e}"
        return status


@router.get("/snapshot")
async def v8_snapshot(
    request: Request,
    format: str = Query("vertex28", description="Output format: vertex28"),
    compression: str = Query("none", description="Compression: none|zstd"),
    limit: Optional[int] = Query(None, ge=1, description="Optional max number of Vertex28 records to return"),
):
    t0 = time.perf_counter()
    # Route A: MUST be crash-proof (no NameError) even when error paths run.
    request_id = request.headers.get("X-Request-Id") or "unknown"
    source_name = "public.universe_assets"
    try:
        diag = _engine_diag()
    except Exception:
        diag = {}

    s = get_v8_status()
    if not s.get("db_ok") or not s.get("schema_ok") or not s.get("ready"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": 503,
                "status": "unavailable",
                "message": "Titan V8 snapshot unavailable.",
                "reason": s.get("reason"),
                "database_url_scheme": s.get("database_url_scheme"),
                "effective_database_url_redacted": redact_database_url(settings.DATABASE_URL or ""),
                "remediation": _snapshot_prereq_remediation(),
                "request_id": request_id,
            },
        )

    dsn = _require_postgres()

    # Dependency preflight: zstd requires zstandard. Do NOT silently fallback.
    zstd_available = True
    if compression == "zstd":
        try:
            import zstandard as _zstd  # type: ignore  # noqa: F401
        except Exception as e:
            zstd_available = False
            raise HTTPException(
                status_code=400,
                detail={
                    "code": 400,
                    "message": "compression=zstd requires zstandard.",
                    "reason": f"{type(e).__name__}: {e}",
                    "remediation": "pip install zstandard",
                    "request_id": request_id,
                },
            )

    if format != "vertex28":
        raise HTTPException(status_code=400, detail={"code": 400, "message": f"Unsupported format: {format}"})

    if compression not in ("none", "zstd"):
        raise HTTPException(status_code=400, detail={"code": 400, "message": f"Unsupported compression: {compression}"})

    def _as_bytes(v) -> bytes:
        if isinstance(v, (bytes, bytearray)):
            return bytes(v)
        # psycopg2 returns BYTEA as memoryview
        try:
            return bytes(v)
        except Exception:
            raise TypeError(f"vertex_buffer is not bytes-like: {type(v).__name__}")

    # Logging/source labels: always use predefined variables (no NameError).
    source = source_name
    row_count = 0
    raw_payload = b""

    t_conn0 = time.perf_counter()
    try:
        with engine.connect() as conn:
            # Connectivity gate: if Postgres is configured but unreachable, return 503 (not 500).
            try:
                conn.execute(text("SELECT 1"))
            except Exception as e:
                logger.exception(
                    "[V8 snapshot] DB unreachable request_id=%s diag=%s",
                    request_id,
                    diag,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": 503,
                        "message": "Titan V8 PostgreSQL is configured but unreachable.",
                        "detected_scheme": parse_db_scheme(dsn),
                        "effective_database_url_redacted": redact_database_url(dsn),
                        "reason": f"{type(e).__name__}: {e}",
                        "remediation": _remediation(),
                        "request_id": request_id,
                    },
                )

            t_conn_ms = int((time.perf_counter() - t_conn0) * 1000)

            # Route A: strict Vertex28 from the MV (required).
            base_q = """
              SELECT vertex_buffer
              FROM public.universe_snapshot_v8
              ORDER BY morton_code ASC
            """
            params = {}
            if limit is not None:
                base_q += " LIMIT :lim"
                params["lim"] = int(limit)

            t_q0 = time.perf_counter()
            try:
                result_rows = conn.execute(text(base_q), params).all()
            except ProgrammingError as e:
                logger.exception(
                    "[V8 snapshot] SQL failed source=%s request_id=%s diag=%s",
                    source_name,
                    request_id,
                    diag,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": 503,
                        "message": f"Snapshot query failed for source={source_name}. Schema may be missing or incompatible.",
                        "reason": f"{type(e).__name__}: {e}",
                        "diagnostics": diag,
                        "remediation": _snapshot_prereq_remediation(),
                        "request_id": request_id,
                    },
                )
            t_q_ms = int((time.perf_counter() - t_q0) * 1000)

            buf = bytearray()
            for (vb,) in result_rows:
                b = _as_bytes(vb)
                if len(b) != VERTEX28_STRIDE:
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": 503,
                            "message": "Vertex28 contract violation: vertex_buffer stride != 28 detected.",
                            "expected_stride": VERTEX28_STRIDE,
                            "actual_len": len(b),
                            "request_id": request_id,
                        },
                    )
                buf.extend(b)
            row_count = len(result_rows)
            raw_payload = bytes(buf)

    except HTTPException:
        raise
    except Exception as e:
        # Unexpected internal error: return 500 (and log full stack trace).
        logger.exception(
            "[V8 snapshot] INTERNAL ERROR request_id=%s diag=%s err=%s",
            request_id,
            diag,
            e,
        )
        raise HTTPException(
            status_code=500,
            detail={
                "code": 500,
                "message": "Internal Server Error (V8 snapshot). See server logs for request_id.",
                "request_id": request_id,
            },
        )

    # Vertex28 post-conditions: total length must match N*28.
    expected_len = int(row_count) * VERTEX28_STRIDE
    if len(raw_payload) != expected_len:
        raise HTTPException(
            status_code=500,
            detail={
                "code": 500,
                "message": "Internal Server Error: snapshot payload length mismatch.",
                "details": {
                    "rows": row_count,
                    "expected_len": expected_len,
                    "actual_len": len(raw_payload),
                    "stride": VERTEX28_STRIDE,
                    "source": "universe_assets",
                },
                "request_id": request_id,
            },
        )

    # Route A contract guard: MUST be multiple of 28 before returning bytes.
    # Validation (DoD): (Get-Item v8_snapshot.bin).Length % 28 -eq 0
    try:
        _ = validate_vertex28_blob(raw_payload)
    except Exception as e:
        # Contract failure: return JSON 503 (not 500 crash).
        raise HTTPException(
            status_code=503,
            detail={
                "code": 503,
                "message": "Vertex28 contract violation: snapshot length is not a multiple of 28.",
                "reason": f"{type(e).__name__}: {e}",
                "source": source_name,
                "rows": row_count,
                "request_id": request_id,
            },
        )

    # Deterministic sample validation (10 records spaced across the payload).
    try:
        from services.vertex28 import unpack_vertex28

        n_samples = min(10, row_count)
        step = max(1, row_count // n_samples)
        for i in range(0, n_samples * step, step):
            off = i * VERTEX28_STRIDE
            rec = raw_payload[off : off + VERTEX28_STRIDE]
            mort_u32, meta32, x, y, z, risk, shock = unpack_vertex28(rec)
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 <= z <= 1.0):
                raise ValueError(f"xyz out of [0,1] range at sample idx={i}: {(x, y, z)}")
            if not (0.0 <= risk <= 1.0):
                raise ValueError(f"risk out of [0,1] range at sample idx={i}: {risk}")
            if not (0.0 <= shock <= 1.0):
                raise ValueError(f"shock out of [0,1] range at sample idx={i}: {shock}")
            _ = (mort_u32, meta32)
    except HTTPException:
        raise
    except Exception as e:
        # Logging must never throw (use predefined vars and guard).
        try:
            logger.exception(
                "[V8 snapshot] contract sample validation failed request_id=%s source=%s diag=%s",
                request_id,
                source_name,
                diag,
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=503,
            detail={
                "code": 503,
                "message": "Vertex28 contract sample validation failed.",
                "reason": f"{type(e).__name__}: {e}",
                "source": source_name,
                "rows": row_count,
                "request_id": request_id,
            },
        )

    payload = raw_payload
    t_comp0 = time.perf_counter()
    if compression == "zstd":
        import zstandard as zstd  # type: ignore

        payload = zstd.ZstdCompressor(level=22).compress(payload)
    t_comp_ms = int((time.perf_counter() - t_comp0) * 1000)

    dt_ms = int((time.perf_counter() - t0) * 1000)
    headers = {
        "X-Titan-Version": "V8",
        "X-Reality-Source": "postgresql",
        "X-Vertex-Stride": str(VERTEX28_STRIDE),
        # Validation convenience (HTTP headers are case-insensitive).
        "x-vertex-stride": str(VERTEX28_STRIDE),
        "X-Points-Count": str(row_count),
        "X-Asset-Count": str(row_count),
        "X-Titan-Source": "universe_assets",
        "X-Request-Id": request_id,
        "Cache-Control": "no-store",
        # Route A required headers
        "x-wsw-stride": str(VERTEX28_STRIDE),
        "x-wsw-format": "vertex28",
        "x-wsw-points-count": str(row_count),
    }
    if compression == "zstd":
        headers["Content-Encoding"] = "zstd"
    headers["X-WSW-Zstd-Available"] = "1" if zstd_available else "0"

    logger.info(
        "[V8 snapshot] source=%s rows=%d compression=%s raw_bytes=%d out_bytes=%d dt_ms=%d comp_ms=%d diag=%s request_id=%s",
        source_name,
        row_count,
        compression,
        len(raw_payload),
        len(payload),
        dt_ms,
        t_comp_ms,
        diag,
        request_id,
    )

    return Response(content=payload, media_type="application/octet-stream", headers=headers)


@router.websocket("/stream")
async def v8_stream(ws: WebSocket):
    # Route A minimal stream: keepalive/heartbeat (no deltas yet).
    await ws.accept()
    _dbg("H4", "api/universe_v8.py:v8_stream", "ws_accept", {"path": "/api/universe/v8/stream"})
    try:
        while True:
            await ws.send_text(f'{{"type":"heartbeat","ts":{int(time.time()*1000)}}}')
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        _dbg("H4", "api/universe_v8.py:v8_stream", "ws_disconnect", {"path": "/api/universe/v8/stream"})
        return

