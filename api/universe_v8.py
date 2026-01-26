from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from config import parse_db_scheme, redact_database_url, settings
from database import engine
from services.vertex28 import VERTEX28_STRIDE
from services.universe_sources import v8_universe_assets_relation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/universe/v8", tags=["quantum"])


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


@router.get("/health")
@router.head("/health")
async def v8_health(request: Request):
    s = get_v8_status()
    v8_ready = bool(s["ready"])
    reason: Optional[str] = s.get("reason")

    if request.method == "HEAD":
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


def _ensure_seed_if_empty_best_effort(min_rows: int = 2000) -> int:
    """
    Best-effort auto-seed to prevent permanent 503s when DB is empty.
    """
    try:
        from database import ensure_min_universe_seed

        return int(ensure_min_universe_seed(int(min_rows)) or 0)
    except Exception:
        return 0


def get_v8_status() -> dict:
    """
    Source-of-truth V8 readiness for both /health and /snapshot.

    ready = db_ok AND schema_ok (rows may be 0).
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
        "assets_view_exists": False,
        "mv_exists": False,
        "diagnostics": diag,
    }
    if scheme != "postgresql":
        status["reason"] = "DATABASE_URL is not PostgreSQL; V8 requires Postgres"
        return status

    rel = v8_universe_assets_relation()
    try:
        # Best-effort bootstrap for canonical V8 relation.
        _ensure_v8_schema_best_effort()

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

            has_table = bool(conn.execute(text(f"SELECT to_regclass('{rel}') IS NOT NULL")).scalar())
            status["schema_ok"] = bool(has_table)
            if not has_table:
                status["reason"] = f"Missing required table {rel}"
                status["ready"] = False
                return status
            try:
                status["rows"] = int(conn.execute(text(f"SELECT COUNT(*) FROM {rel}")).scalar() or 0)
            except Exception:
                status["rows"] = 0

            # Vertex28 contract gate: require at least 1 row AND a 28-byte vertex_buffer invariant.
            if status["rows"] <= 0:
                status["ready"] = False
                status["reason"] = "universe_assets empty; run seeding/materialization"
                return status

            try:
                # Cheap sample: verify at least one 28-byte buffer exists.
                ok_any = bool(
                    conn.execute(
                        text(f"SELECT EXISTS(SELECT 1 FROM {rel} WHERE octet_length(vertex_buffer)=:n)"),
                        {"n": int(VERTEX28_STRIDE)},
                    ).scalar()
                )
            except Exception:
                ok_any = False

            if not ok_any:
                status["ready"] = False
                status["reason"] = f"vertex_buffer stride mismatch (expected {VERTEX28_STRIDE})"
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
    compression: str = Query("zstd", description="Compression: zstd|none"),
    limit: Optional[int] = Query(None, ge=1, description="Optional max number of Vertex28 records to return"),
):
    t0 = time.perf_counter()
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    diag = _engine_diag()

    # Gate with the same deterministic readiness used by /health.
    # If not ready, return a structured 503 with remediation.
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
                status_code=503,
                detail={
                    "code": 503,
                    "message": "compression=zstd requires zstandard.",
                    "reason": f"{type(e).__name__}: {e}",
                    "remediation": "pip install zstandard",
                    "request_id": request_id,
                },
            )

    if format != "vertex28":
        raise HTTPException(status_code=400, detail={"code": 400, "message": f"Unsupported format: {format}"})

    if compression not in ("zstd", "none"):
        raise HTTPException(status_code=400, detail={"code": 400, "message": f"Unsupported compression: {compression}"})

    def _as_bytes(v) -> bytes:
        if isinstance(v, (bytes, bytearray)):
            return bytes(v)
        # psycopg2 returns BYTEA as memoryview
        try:
            return bytes(v)
        except Exception:
            raise TypeError(f"vertex_buffer is not bytes-like: {type(v).__name__}")

    source = "unknown"
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

            # Preflight: verify required objects and columns exist.
            has_mv = bool(
                conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": "public.universe_snapshot_v8"}).scalar()
            )
            has_table = bool(
                conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": "public.universe_assets"}).scalar()
            )

            if has_mv:
                source = "universe_snapshot_v8"
                table_for_columns = "universe_snapshot_v8"
            elif has_table:
                source = "universe_assets"
                table_for_columns = "universe_assets"
            else:
                # Auto-bootstrap attempt (idempotent) before returning 503.
                try:
                    from database import init_database

                    init_database()
                except Exception:
                    pass
                has_mv = bool(
                    conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": "public.universe_snapshot_v8"}).scalar()
                )
                has_table = bool(
                    conn.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": "public.universe_assets"}).scalar()
                )
                if has_mv:
                    source = "universe_snapshot_v8"
                    table_for_columns = "universe_snapshot_v8"
                elif has_table:
                    source = "universe_assets"
                    table_for_columns = "universe_assets"
                else:
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": 503,
                            "message": "Titan V8 snapshot prerequisites missing: no snapshot source exists.",
                            "details": {
                                "has_universe_snapshot_v8": bool(has_mv),
                                "has_universe_assets": bool(has_table),
                            },
                            "diagnostics": diag,
                            "remediation": _snapshot_prereq_remediation(),
                            "request_id": request_id,
                        },
                    )

            cols = conn.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema='public' AND table_name = :t
                    """
                ),
                {"t": table_for_columns},
            ).mappings().all()
            colset = {r["column_name"] for r in cols}
            missing_cols = [c for c in ("morton_code", "vertex_buffer") if c not in colset]
            if missing_cols:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": 503,
                        "message": f"Snapshot prerequisites missing: {source} is missing required columns.",
                        "details": {
                            "source": source,
                            "missing_columns": missing_cols,
                            "present_columns": sorted(list(colset))[:50],
                        },
                        "diagnostics": diag,
                        "remediation": _snapshot_prereq_remediation(),
                        "request_id": request_id,
                    },
                )

            # Deterministic query order
            base_q = f"SELECT morton_code, vertex_buffer FROM public.{source} ORDER BY morton_code ASC"
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
                    source,
                    request_id,
                    diag,
                )
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": 503,
                        "message": f"Snapshot query failed for source={source}. Schema may be missing or incompatible.",
                        "reason": f"{type(e).__name__}: {e}",
                        "diagnostics": diag,
                        "remediation": _snapshot_prereq_remediation(),
                        "request_id": request_id,
                    },
                )
            t_q_ms = int((time.perf_counter() - t_q0) * 1000)

            # Validate stride + Morton uniqueness while assembling payload.
            buf = bytearray()
            min_len: Optional[int] = None
            max_len: Optional[int] = None
            bad = 0
            seen_morton: set[int] = set()
            collisions: list[int] = []

            for mc, vb in result_rows:
                mc_i = int(mc)
                if mc_i in seen_morton and len(collisions) < 10:
                    collisions.append(mc_i)
                seen_morton.add(mc_i)

                b = _as_bytes(vb)
                n = len(b)
                min_len = n if (min_len is None or n < min_len) else min_len
                max_len = n if (max_len is None or n > max_len) else max_len
                if n != VERTEX28_STRIDE:
                    bad += 1
                buf.extend(b)

            row_count = len(result_rows)

            if row_count == 0:
                # Auto-seed minimal universe and retry ONCE (fast path to unblock UI today).
                seeded = _ensure_seed_if_empty_best_effort(2000)
                if seeded > 0:
                    source = "universe_assets"
                    result_rows = conn.execute(
                        text(
                            "SELECT morton_code, vertex_buffer FROM public.universe_assets ORDER BY morton_code ASC"
                            + (" LIMIT :lim" if limit is not None else "")
                        ),
                        {"lim": int(limit)} if limit is not None else {},
                    ).all()
                    buf = bytearray()
                    for mc, vb in result_rows:
                        buf.extend(_as_bytes(vb))
                    raw_payload = bytes(buf)
                    row_count = len(result_rows)
                if row_count == 0:
                    dt_ms = int((time.perf_counter() - t0) * 1000)
                    logger.info(
                        "[V8 snapshot] source=%s rows=0 compression=%s bytes=0 dt_ms=%d conn_ms=%d query_ms=%d request_id=%s diag=%s",
                        source,
                        compression,
                        dt_ms,
                        t_conn_ms,
                        t_q_ms,
                        request_id,
                        diag,
                    )
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "code": 503,
                            "status": "unavailable",
                            "message": "Titan V8 snapshot has no data (0 rows) even after auto-seed attempt.",
                            "reason": "universe_assets empty",
                            "source": source,
                            "diagnostics": diag,
                            "remediation": _snapshot_prereq_remediation(),
                            "request_id": request_id,
                        },
                    )

            if bad != 0:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": 422,
                        "message": "Vertex28 contract violation: vertex_buffer stride != 28 detected.",
                        "source": source,
                        "rows": row_count,
                        "expected_stride": VERTEX28_STRIDE,
                        "min_len": min_len,
                        "max_len": max_len,
                        "bad_count": bad,
                        "diagnostics": diag,
                        "request_id": request_id,
                    },
                )

            if collisions:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": 422,
                        "message": "Morton63 collision detected in snapshot source (duplicate morton_code).",
                        "source": source,
                        "rows": row_count,
                        "collisions_sample": collisions,
                        "diagnostics": diag,
                        "request_id": request_id,
                    },
                )

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
                    "source": source,
                },
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
            tax, meta, x, y, z, fid, spin = unpack_vertex28(rec)
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 and 0.0 <= z <= 1.0):
                raise ValueError(f"xyz out of [0,1] range at sample idx={i}: {(x, y, z)}")
            if not (0.0 <= fid <= 1.0):
                raise ValueError(f"fidelity out of [0,1] range at sample idx={i}: {fid}")
            # tax/meta are uint32; no further constraint here
            _ = (tax, meta, spin)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "[V8 snapshot] contract sample validation failed request_id=%s source=%s diag=%s",
            request_id,
            source,
            diag,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "code": 422,
                "message": "Vertex28 contract sample validation failed.",
                "reason": f"{type(e).__name__}: {e}",
                "source": source,
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
        "X-Asset-Count": str(row_count),
        "X-Titan-Source": source,
        "X-Request-Id": request_id,
        "Cache-Control": "no-store",
        "X-WSW-Format": "vertex28",
        "X-WSW-Points-Count": str(row_count),
    }
    if compression == "zstd":
        headers["Content-Encoding"] = "zstd"
    headers["X-WSW-Zstd-Available"] = "1" if zstd_available else "0"

    logger.info(
        "[V8 snapshot] source=%s rows=%d compression=%s raw_bytes=%d out_bytes=%d dt_ms=%d comp_ms=%d diag=%s request_id=%s",
        source,
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

