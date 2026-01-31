from __future__ import annotations

"""
Route A: TITAN V8 Universe API Router (PostgreSQL-only + Vertex28-only).

This module is a thin wrapper around the canonical router in `api.universe_v8`.
Legacy formats/endpoints/encoders are intentionally not present.
"""

from api.universe_v8 import router  # noqa: F401

"""
Titan V8 Universe API Router
Quantum endpoints for sovereign universe orchestration.
"""
from __future__ import annotations
import asyncio
import logging
import os
import struct
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, Response, Request
from fastapi.responses import Response as FastAPIResponse, JSONResponse
from typing import Dict, Any
import uuid

# Import orchestrator and models
import sys
from pathlib import Path
root_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_path))

try:
    from backend.services.sovereign_orchestrator import (
        SovereignOrchestrator,
        UniverseSnapshot,
        UniverseDeltaProtocol,
    )
    from backend.models.universe import VertexLayout28, UniverseAsset
    ORCHESTRATOR_AVAILABLE = True
except ImportError as e:
    ORCHESTRATOR_AVAILABLE = False
    ORCHESTRATOR_IMPORT_ERROR = str(e)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/universe/v8", tags=["quantum"])

# Legacy points.bin struct: stride 12, <HHII
_LEGACY_POINTS_STRUCT = struct.Struct("<HHII")  # uint16 x, uint16 y, uint32 taxonomy32, uint32 meta32


def redact_database_url(url: str) -> str:
    """Redact password from database URL for safe logging"""
    if not url:
        return url
    try:
        if '@' in url:
            parts = url.split('@')
            if len(parts) == 2:
                auth_part = parts[0]
                rest = parts[1]
                if '://' in auth_part:
                    scheme_part = auth_part.split('://')[0] + '://'
                    creds = auth_part.split('://')[1]
                    if ':' in creds:
                        user = creds.split(':')[0]
                        return f"{scheme_part}{user}:***@{rest}"
                    return f"{scheme_part}***@{rest}"
        return url
    except Exception:
        return url[:50] + "..." if len(url) > 50 else url


def parse_db_scheme(url: str) -> str:
    """Extract database scheme from URL"""
    if not url:
        return "unknown"
    url_lower = url.lower()
    if url_lower.startswith("postgresql") or url_lower.startswith("postgres"):
        return "postgresql"
    elif url_lower.startswith("sqlite"):
        return "sqlite"
    return "unknown"

def normalize_postgres_dsn(url: str) -> str:
    """Normalize SQLAlchemy-style DSNs to plain postgresql:// for connectivity checks."""
    if not url:
        return url
    u = url.strip()
    if u.startswith("postgresql+psycopg://"):
        return "postgresql://" + u[len("postgresql+psycopg://"):]
    if u.startswith("postgresql+psycopg2://"):
        return "postgresql://" + u[len("postgresql+psycopg2://"):]
    if u.startswith("postgres://"):
        return "postgresql://" + u[len("postgres://"):]
    return u


def get_v8_remediation() -> Dict[str, str]:
    """Get remediation instructions for V8 availability"""
    return {
        "windows_powershell": (
            "$env:DATABASE_URL=\"postgresql://postgres:postgres@localhost:5432/wsw_db\"\n"
            "python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
        ),
        "docker_networking": (
            "postgresql://postgres:postgres@wsw-postgres:5432/wsw_db"
        )
    }


class SovereignFailure(Exception):
    """Exception raised when essential dependencies are missing"""
    def __init__(self, dep_name: str):
        self.dep_name = dep_name
        super().__init__(f"Sovereign dependency missing: {dep_name}. Install: pip install {dep_name}")


# Orchestrator singleton
_orchestrator: Optional[SovereignOrchestrator] = None
_orchestrator_lock = asyncio.Lock()
_orchestrator_started = False


async def get_orchestrator() -> SovereignOrchestrator:
    """
    Get or create orchestrator singleton.
    Requires: asyncpg, pyarrow, zstandard, msgpack
    """
    global _orchestrator, _orchestrator_started
    
    if not ORCHESTRATOR_AVAILABLE:
        raise SovereignFailure("backend.services.sovereign_orchestrator")
    
    # Check essential dependencies
    deps = {
        "asyncpg": "asyncpg",
        "pyarrow": "pyarrow",
        "zstandard": "zstandard",
        "msgpack": "msgpack",
    }
    
    for dep_name, package_name in deps.items():
        try:
            __import__(dep_name)
        except ImportError:
            raise SovereignFailure(package_name)
    
    async with _orchestrator_lock:
        if _orchestrator is None:
            from config import settings
            dsn = settings.DATABASE_URL
            detected_scheme = parse_db_scheme(dsn)
            if not dsn or detected_scheme == "sqlite":
                remediation = get_v8_remediation()
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": 503,
                        "message": "Titan V8 requires PostgreSQL. DATABASE_URL must be a PostgreSQL connection string.",
                        "detected_scheme": detected_scheme,
                        "effective_database_url_redacted": redact_database_url(dsn),
                        "remediation": remediation,
                        "request_id": str(uuid.uuid4())
                    }
                )

            try:
                _orchestrator = SovereignOrchestrator(dsn=dsn)
                await _orchestrator.start()
            except Exception as e:
                remediation = get_v8_remediation()
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": 503,
                        "message": "Titan V8 PostgreSQL is configured but unreachable. Fix DATABASE_URL or Postgres connectivity.",
                        "detected_scheme": detected_scheme,
                        "effective_database_url_redacted": redact_database_url(dsn),
                        "reason": f"{type(e).__name__}: {e}",
                        "remediation": remediation,
                        "request_id": str(uuid.uuid4())
                    }
                )

            _orchestrator_started = True
            logger.info("SovereignOrchestrator started")
        
        return _orchestrator


@router.get("/health")
@router.head("/health")
async def get_v8_health(request: Request):
    """
    V8 health check endpoint.
    Returns 200 if V8 is ready, 503 if unavailable.
    """
    from config import settings
    dsn = settings.DATABASE_URL
    detected_scheme = parse_db_scheme(dsn)
    is_healthy = False
    reason: Optional[str] = None

    if detected_scheme == "postgresql":
        # Best-effort reachability check (fast) without starting the orchestrator
        try:
            import asyncpg  # type: ignore
            conn = await asyncpg.connect(normalize_postgres_dsn(dsn), timeout=1)
            await conn.close()
            is_healthy = True
        except Exception as e:
            is_healthy = False
            reason = f"PostgreSQL unreachable: {type(e).__name__}: {e}"
    else:
        reason = f"DATABASE_URL uses {detected_scheme}; V8 requires PostgreSQL"
    
    if request.method == "HEAD":
        status_code = 200 if is_healthy else 503
        return Response(status_code=status_code)
    
    remediation = get_v8_remediation() if not is_healthy else None
    
    response_data = {
        "status": "healthy" if is_healthy else "unavailable",
        "v8_ready": bool(is_healthy),
        "database_url_scheme": detected_scheme,
        "database_url_effective": redact_database_url(dsn),
        "effective_database_url_redacted": redact_database_url(dsn),
        "reason": reason,
        "remediation": remediation
    }
    
    status_code = 200 if is_healthy else 503
    return JSONResponse(content=response_data, status_code=status_code)


@router.get("/snapshot")
async def get_snapshot(
    format: str = Query("vertex28", description="Output format: vertex28|arrow|flatbuffer"),
    compression: str = Query("zstd", description="Compression: zstd|none"),
):
    """
    Get universe snapshot in specified format.
    Returns 200 with payload or 204 if no data available.
    """
    try:
        orchestrator = await get_orchestrator()
    except HTTPException:
        # Re-raise HTTPException (already has enriched 503 detail)
        raise
    except SovereignFailure as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    try:
        snapshot = await orchestrator.build_snapshot(limit=10000)
    except Exception as e:
        logger.exception(f"[snapshot] build_snapshot failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Snapshot build failed: {type(e).__name__}")
    
    # Handle empty snapshot
    if not snapshot.assets:
        from config import settings
        # If DEBUG, Sentinel/Ambassador tiers should still produce data
        # If truly empty and not DEBUG, return 204
        if not settings.DEBUG:
            return Response(status_code=204, content=b"", media_type="application/octet-stream")
        # DEBUG: try Sentinel tier explicitly
        try:
            # Force Sentinel tier (deterministic, always produces data)
            snapshot = await orchestrator.build_snapshot(limit=100)
            if not snapshot.assets:
                return Response(status_code=204, content=b"", media_type="application/octet-stream")
        except Exception:
            return Response(status_code=204, content=b"", media_type="application/octet-stream")
    
    # Format selection
    if format == "vertex28":
        data = snapshot.vertex_bytes
        media_type = "application/octet-stream"
    elif format == "arrow":
        try:
            data = orchestrator.to_arrow_ipc(snapshot)
            media_type = "application/vnd.apache.arrow.ipc"
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
    elif format == "flatbuffer":
        try:
            data = orchestrator.to_flatbuffer_snapshot(snapshot)
            media_type = "application/octet-stream"
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail=f"Invalid format: {format}. Use vertex28|arrow|flatbuffer")
    
    # Compression
    if compression == "zstd":
        try:
            import zstandard as zstd
            cctx = zstd.ZstdCompressor(level=22)
            data = cctx.compress(data)
            headers = {
                "Content-Encoding": "zstd",
                "X-Titan-Version": "V8",
                "X-Reality-Source": "sovereign_universe",
                "X-Vertex-Stride": "28",
                "X-Asset-Count": str(len(snapshot.assets)),
                "X-Fidelity-Min": f"{min(a.fidelity_score for a in snapshot.assets):.3f}" if snapshot.assets else "n/a",
                "Cache-Control": "no-store",
            }
        except ImportError:
            raise HTTPException(status_code=503, detail="zstandard required for compression=zstd")
    else:
        headers = {
            "X-Titan-Version": "V8",
            "X-Reality-Source": "sovereign_universe",
            "X-Vertex-Stride": "28",
            "X-Asset-Count": str(len(snapshot.assets)),
            "X-Fidelity-Min": f"{min(a.fidelity_score for a in snapshot.assets):.3f}" if snapshot.assets else "n/a",
            "Cache-Control": "no-store",
        }
    
    return Response(content=data, media_type=media_type, headers=headers)


@router.websocket("/stream")
async def websocket_stream(websocket: WebSocket):
    """
    WebSocket stream at 10Hz with MessagePack + zstd deltas.
    """
    await websocket.accept()
    
    try:
        orchestrator = await get_orchestrator()
    except SovereignFailure as e:
        await websocket.close(code=1008, reason=str(e))
        return
    
    try:
        async for delta_bytes in orchestrator.stream_universe_10hz():
            await websocket.send_bytes(delta_bytes)
    except WebSocketDisconnect:
        logger.info("[stream] WebSocket disconnected")
    except Exception as e:
        logger.exception(f"[stream] Error: {type(e).__name__}: {e}")
        await websocket.close(code=1011, reason=f"Stream error: {type(e).__name__}")


@router.get("/points.bin")
async def get_points_bin_legacy():
    """
    Legacy /points.bin endpoint matching existing contract.
    Stride 12 bytes: <HHII (uint16 x, uint16 y, uint32 taxonomy32, uint32 meta32)
    """
    try:
        orchestrator = await get_orchestrator()
    except SovereignFailure as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    try:
        snapshot = await orchestrator.build_snapshot(limit=10000)
    except Exception as e:
        logger.exception(f"[points.bin] build_snapshot failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Snapshot build failed: {type(e).__name__}")
    
    if not snapshot.assets:
        return Response(status_code=204, content=b"", media_type="application/octet-stream")
    
    # Convert UniverseAsset to legacy format
    n = len(snapshot.assets)
    buffer = bytearray(n * 12)  # stride 12
    mv = memoryview(buffer)
    
    for i, asset in enumerate(snapshot.assets):
        offset = i * 12
        
        # Convert x, y floats to uint16
        # Heuristic: if 0 <= x <= 1.5, treat as normalized [0,1]
        if 0.0 <= asset.x <= 1.5:
            x_u16 = int(max(0, min(65535, asset.x * 65535))) & 0xFFFF
        else:
            x_u16 = int(max(0, min(65535, asset.x))) & 0xFFFF
        
        if 0.0 <= asset.y <= 1.5:
            y_u16 = int(max(0, min(65535, asset.y * 65535))) & 0xFFFF
        else:
            y_u16 = int(max(0, min(65535, asset.y))) & 0xFFFF
        
        # Pack: <HHII
        _LEGACY_POINTS_STRUCT.pack_into(
            mv, offset,
            x_u16,
            y_u16,
            asset.taxonomy32 & 0xFFFFFFFF,
            asset.meta32 & 0xFFFFFFFF,
        )
    
    return Response(
        content=bytes(buffer),
        media_type="application/octet-stream",
        headers={
            "X-Legacy-Stride": "12",
            "Cache-Control": "no-store",
        }
    )
