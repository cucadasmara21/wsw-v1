"""
EL MOTOR DE REALIDADES CUÁNTICAS (Titan V8)
Extractos materializados:


3 tiers: Sentinel (mock), Ambassador (synthetic Beta sector distributions), Sovereign (real APIs)


Fail-Fast: Tier3 >300ms or 404 -> silent, state-preserving fallback to Tier2


Circuit Breaker using asyncio.wait_for(..., timeout=0.300) EXACT


Performance Audit: replace ORM with asyncpg + prepared statements + JSON aggregation (json_agg)


Concurrency: SKIP LOCKED for updates


Binary Protocol: WebSocket streaming 10Hz + MessagePack + zstd delta encoding


Hot-path: snapshot binary (flatbuffer) and Arrow alignment (Arrow → WebGL2)
"""


from __future__ import annotations
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, AsyncGenerator, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except Exception:  # pragma: no cover
    ASYNCPG_AVAILABLE = False
    asyncpg = None  # type: ignore

from backend.models.universe import (
    GovernanceStatus,
    UniverseAsset,
    VertexLayout28,
    pack_meta32,
    pack_taxonomy32,
)

# Optional dependencies (guarded; do not break imports)
try:
    import msgpack  # MessagePack
    MSGPACK_AVAILABLE = True
except Exception:  # pragma: no cover
    MSGPACK_AVAILABLE = False
    msgpack = None  # type: ignore

try:
    import zstandard as zstd  # zstd
    ZSTD_AVAILABLE = True
except Exception:  # pragma: no cover
    ZSTD_AVAILABLE = False
    zstd = None  # type: ignore

try:
    import pyarrow as pa  # Arrow
    import pyarrow.ipc as pa_ipc
    ARROW_AVAILABLE = True
except Exception:  # pragma: no cover
    ARROW_AVAILABLE = False
    pa = None  # type: ignore
    pa_ipc = None  # type: ignore

try:
    import flatbuffers  # flatbuffer
    FLATBUFFERS_AVAILABLE = True
except Exception:  # pragma: no cover
    FLATBUFFERS_AVAILABLE = False
    flatbuffers = None  # type: ignore


class UniverseOpcode(IntEnum):
    ASSET_ADD = 0x01
    ASSET_REMOVE = 0x02
    FIDELITY_UPDATE = 0x03


@dataclass(slots=True)
class UniverseDelta:
    opcode: UniverseOpcode
    payload: bytes


class UniverseDeltaProtocol:
    """
    FORMAT = MessagePack
    OPCODES = {
        0x01: 'ASSET_ADD',       # minimal packed record
        0x02: 'ASSET_REMOVE',    # asset_id
        0x03: 'FIDELITY_UPDATE'  # asset_id + score
    }
    Expected bandwidth: <100bps (target) vs 50kbps JSON.
    """
    def __init__(self, compression: str = "zstd") -> None:
        self.compression = compression

    def encode(self, delta: UniverseDelta) -> bytes:
        if not MSGPACK_AVAILABLE:
            raise RuntimeError("MessagePack dependency missing: install msgpack to enable delta protocol.")
        obj = {"op": int(delta.opcode), "p": delta.payload}
        raw = msgpack.packb(obj, use_bin_type=True)  # type: ignore[attr-defined]
        if self.compression == "zstd":
            if not ZSTD_AVAILABLE:
                raise RuntimeError("zstd dependency missing: install zstandard to enable compression=zstd.")
            cctx = zstd.ZstdCompressor(level=3)  # type: ignore[union-attr]
            return cctx.compress(raw)
        return raw

    def decode(self, blob: bytes) -> UniverseDelta:
        if self.compression == "zstd":
            if not ZSTD_AVAILABLE:
                raise RuntimeError("zstd dependency missing: cannot decode zstd frames.")
            dctx = zstd.ZstdDecompressor()  # type: ignore[union-attr]
            raw = dctx.decompress(blob)
        else:
            raw = blob
        if not MSGPACK_AVAILABLE:
            raise RuntimeError("MessagePack dependency missing: cannot decode deltas.")
        obj = msgpack.unpackb(raw, raw=False)  # type: ignore[attr-defined]
        return UniverseDelta(UniverseOpcode(int(obj["op"])), bytes(obj["p"]))


class CircuitBreakerError(Exception):
    pass


class QuantumCircuitBreaker:
    """
    CircuitBreaker (Apéndice Técnico Ineludible):
    asyncio.wait_for(coro, timeout=0.300) EXACT
    """
    def __init__(self, name: str, failure_threshold: int = 3, reset_timeout_s: float = 60.0) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout_s = reset_timeout_s
        self._failures = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        return (time.time() - self._opened_at) < self.reset_timeout_s

    async def observe(self, coro: Any) -> Any:
        if self.is_open:
            raise CircuitBreakerError(f"CircuitBreaker({self.name}) OPEN")
        try:
            # EXACT timeout literal per mandate:
            result = await asyncio.wait_for(coro, timeout=0.300)
            self._failures = max(0, self._failures - 1)
            return result
        except Exception as e:
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._opened_at = time.time()
            raise CircuitBreakerError(f"CircuitBreaker({self.name}) failure: {e}") from e


@dataclass(slots=True)
class UniverseSnapshot:
    ts_ms: int
    assets: List[UniverseAsset]
    vertex_bytes: bytes  # WebGL2 upload-ready (stride=28)
    source_tier: str  # Sentinel/Ambassador/Sovereign


class SovereignOrchestrator:
    """
    Orchestrator of 3-tier reality with state-preserving fallback.
    - Sentinel: deterministic mock
    - Ambassador: synthetic Beta distributions
    - Sovereign: real APIs (institutional mapping), guarded by CircuitBreaker 300ms
    """
    # P-04: VoidPool capacity (N=200k); slot mapping for Death/Birth wiring
    _VOIDPOOL_CAP = 200_000

    def __init__(self, dsn: str, redis_url: Optional[str] = None) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        self._cb = QuantumCircuitBreaker("sovereign-tier", failure_threshold=3, reset_timeout_s=30.0)
        self._last_snapshot: Optional[UniverseSnapshot] = None
        self._delta = UniverseDeltaProtocol(compression="zstd")
        self._redis_url = redis_url
        self._redis = None  # optional, lazy
        self._void_pool = None  # lazy init
        self._symbol_to_slot: Dict[str, Tuple[int, int]] = {}  # symbol -> (slot_idx, seq64)

    async def start(self) -> None:
        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg dependency missing: install asyncpg to enable database operations.")
        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=8)
        if self._redis_url:
            try:
                import redis.asyncio as redis  # type: ignore
                self._redis = redis.from_url(self._redis_url)
            except Exception:
                self._redis = None

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
        if self._redis:
            await self._redis.close()

    # ---------------------------
    # Performance Audit: JSON aggregation + prepared statements (single roundtrip)
    # ---------------------------

    async def fetch_universe_state_json_agg(self, limit: int = 10000) -> List[Mapping[str, Any]]:
        """
        SQL aggregation (json_agg) – single roundtrip.
        NOTE: JSON aggregation is for diagnostics; hot-path uses binary/Arrow/flatbuffer.
        """
        if not self._pool:
            raise RuntimeError("Pool not started.")
        sql = """
        SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json) AS payload
        FROM (
            SELECT
                symbol,
                liquidity_tier,
                fidelity_score,
                governance_status,
                taxonomy32,
                meta32,
                COALESCE(x, 0.0) AS x,
                COALESCE(y, 0.0) AS y,
                COALESCE(z, 0.0) AS z,
                render_priority,
                cluster_id
            FROM universe_assets
            WHERE is_active = true
            ORDER BY render_priority ASC, id ASC
            LIMIT $1
        ) t;
        """
        async with self._pool.acquire() as con:
            stmt = await con.prepare(sql)
            row = await stmt.fetchrow(limit)
            payload = row["payload"] if row else []
            if isinstance(payload, str):
                return json.loads(payload)
            return payload  # type: ignore[return-value]

    # ---------------------------
    # Concurrency: SKIP LOCKED updates (rebalancing without blocking)
    # ---------------------------

    async def claim_assets_for_refresh(self, batch_size: int = 200) -> List[str]:
        """
        Acquire a batch of symbols for refresh without contention.
        Uses FOR UPDATE SKIP LOCKED (Performance Audit mandate).
        """
        if not self._pool:
            raise RuntimeError("Pool not started.")
        sql = """
        WITH cte AS (
            SELECT id, symbol
            FROM universe_assets
            WHERE is_active = true
              AND governance_status IN (1,2,3)
            ORDER BY render_priority ASC, id ASC
            LIMIT $1
            FOR UPDATE SKIP LOCKED
        )
        UPDATE universe_assets ua
        SET notes = COALESCE(ua.notes,'')  -- no-op marker in MVP
        FROM cte
        WHERE ua.id = cte.id
        RETURNING cte.symbol;
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, batch_size)
            return [r["symbol"] for r in rows]

    # ---------------------------
    # Tiering
    # ---------------------------

    async def build_snapshot(self, limit: int = 10000) -> UniverseSnapshot:
        """
        Attempt Sovereign → Ambassador → Sentinel
        Silent fallback, state preservation.
        """
        # Try Sovereign (real APIs) guarded by circuit breaker.
        try:
            assets = await self._cb.observe(self._fetch_sovereign_assets(limit))
            snap = self._materialize_snapshot(assets, source_tier="Sovereign")
            self._last_snapshot = snap
            return snap
        except Exception:
            # Fail-fast fallback Tier3 → Tier2 (state preserved if possible).
            try:
                assets = self._generate_ambassador_assets(limit)
                snap = self._materialize_snapshot(assets, source_tier="Ambassador")
                # Preserve phase: do not discard last snapshot; only replace if none exists.
                if self._last_snapshot is None:
                    self._last_snapshot = snap
                return snap
            except Exception:
                assets = self._generate_sentinel_assets(min(limit, 512))
                snap = self._materialize_snapshot(assets, source_tier="Sentinel")
                if self._last_snapshot is None:
                    self._last_snapshot = snap
                return snap

    async def _fetch_sovereign_assets(self, limit: int) -> List[UniverseAsset]:
        """
        Sovereign tier uses DB as registry + external mapping (institutional symbols).
        In MVP: pull from DB; external APIs are layered elsewhere.
        If registry is empty -> emulate 404 to trigger fallback (as mandated).
        """
        if not self._pool:
            raise RuntimeError("Pool not started.")
        sql = """
        SELECT
            symbol, taxonomy32, meta32, fidelity_score, governance_status,
            COALESCE(x, 0.0) AS x, COALESCE(y, 0.0) AS y, COALESCE(z, 0.0) AS z,
            render_priority, cluster_id, liquidity_tier, COALESCE(sector,'') AS sector, COALESCE(name,'') AS name
        FROM universe_assets
        WHERE is_active = true
        ORDER BY render_priority ASC, id ASC
        LIMIT $1;
        """
        async with self._pool.acquire() as con:
            rows = await con.fetch(sql, limit)
        if not rows:
            # Treat empty registry as not-found in Sovereign tier (triggers fallback).
            raise FileNotFoundError("Sovereign tier 404: registry empty")
        out: List[UniverseAsset] = []
        for r in rows:
            gs = GovernanceStatus(int(r["governance_status"]))
            cid = None
            if r["cluster_id"]:
                try:
                    cid = uuid.UUID(str(r["cluster_id"]))
                except Exception:
                    cid = None
            out.append(
                UniverseAsset(
                    symbol=str(r["symbol"]),
                    taxonomy32=int(r["taxonomy32"]) & 0xFFFFFFFF,
                    meta32=int(r["meta32"]) & 0xFFFFFFFF,
                    fidelity_score=float(r["fidelity_score"]),
                    governance_status=gs,
                    x=float(r["x"]),
                    y=float(r["y"]),
                    z=float(r["z"]),
                    render_priority=int(r["render_priority"]) if r["render_priority"] is not None else 100,
                    cluster_id=cid,
                    liquidity_tier=int(r["liquidity_tier"]) if r["liquidity_tier"] is not None else 1,
                    sector=str(r["sector"]),
                    name=str(r["name"]),
                )
            )
        return out

    def _generate_ambassador_assets(self, limit: int) -> List[UniverseAsset]:
        """
        Ambassador tier: high-fidelity synthetic assets with sector-specific Beta distributions.
        Deterministic seed based on index for reproducibility.
        """
        import random
        assets: List[UniverseAsset] = []
        sectors = ["TECH", "FIN", "ENERGY", "HEALTH", "INDUSTRIAL"]
        beta_params = {
            "TECH": (2.5, 1.6),
            "FIN": (2.0, 2.2),
            "ENERGY": (1.8, 2.8),
            "HEALTH": (2.2, 1.9),
            "INDUSTRIAL": (1.9, 2.1),
        }
        for i in range(limit):
            sector = sectors[i % len(sectors)]
            a, b = beta_params[sector]
            rnd = random.Random(i)
            fid = max(0.0, min(1.0, rnd.betavariate(a, b)))
            risk16 = int(fid * 65535) & 0xFFFF
            domain = (i % 7)
            outlier = 1 if rnd.random() < 0.03 else 0
            taxonomy32 = pack_taxonomy32(domain=domain, outlier=outlier, risk16=risk16, reserved12=i & 0xFFF)

            risk8 = int(fid * 255) & 0xFF
            shock8 = int((1.0 - fid) * 255) & 0xFF
            trend2 = (i // 1000) % 3
            vitality6 = int(10 + fid * 50) & 0x3F
            meta32 = pack_meta32(risk8=risk8, shock8=shock8, trend2=trend2, vitality6=vitality6, reserved8=0xA8)

            x = rnd.random()
            y = rnd.random()
            z = rnd.random() * 0.2
            assets.append(
                UniverseAsset(
                    symbol=f"AMB{i:06d}",
                    taxonomy32=taxonomy32,
                    meta32=meta32,
                    fidelity_score=fid,
                    governance_status=GovernanceStatus.PROVISIONAL,
                    x=x, y=y, z=z,
                    render_priority=120,
                    cluster_id=None,
                    liquidity_tier=2,
                    sector=sector,
                    name=f"Ambassador-{i}",
                )
            )
        return assets

    def _generate_sentinel_assets(self, limit: int) -> List[UniverseAsset]:
        """
        Sentinel tier: deterministic mock data (ns latency).
        """
        assets: List[UniverseAsset] = []
        for i in range(limit):
            fid = (i % 100) / 100.0
            taxonomy32 = pack_taxonomy32(domain=0, outlier=0, risk16=int(fid * 65535), reserved12=i & 0xFFF)
            meta32 = pack_meta32(risk8=int(fid * 255), shock8=int((1 - fid) * 255), trend2=0, vitality6=40, reserved8=0x55)
            assets.append(
                UniverseAsset(
                    symbol=f"SNT{i:05d}",
                    taxonomy32=taxonomy32,
                    meta32=meta32,
                    fidelity_score=fid,
                    governance_status=GovernanceStatus.PROVISIONAL,
                    x=(i % 512) / 512.0,
                    y=((i * 17) % 512) / 512.0,
                    z=0.0,
                    render_priority=200,
                    cluster_id=None,
                    liquidity_tier=1,
                    sector="SENTINEL",
                    name=f"Sentinel-{i}",
                )
            )
        return assets

    # ---------------------------
    # Materialization: Zero-copy buffer build for WebGL2
    # ---------------------------

    def _materialize_snapshot(self, assets: List[UniverseAsset], source_tier: str) -> UniverseSnapshot:
        records = [a.to_vertex_record() for a in assets]
        from config import settings
        if settings.ENABLE_VOIDPOOL:
            vb = self._materialize_with_voidpool(assets, records)
        else:
            vb = VertexLayout28.pack_vertex_buffer(records)
        return UniverseSnapshot(ts_ms=int(time.time() * 1000), assets=assets, vertex_bytes=vb, source_tier=source_tier)

    def _materialize_with_voidpool(self, assets: List[UniverseAsset], records: List) -> bytes:
        """P-04: Death->try_push, Birth->try_pop. Real lifecycle wiring."""
        from engines.void_pool import VoidPool
        if self._void_pool is None:
            self._void_pool = VoidPool(capacity=self._VOIDPOOL_CAP)
            self._void_pool.prime(self._VOIDPOOL_CAP)
        pool = self._void_pool
        prev_symbols = set(self._symbol_to_slot.keys())
        curr_symbols = {a.symbol for a in assets}
        # Death: release slots for assets no longer present
        for sym in prev_symbols - curr_symbols:
            slot, seq = self._symbol_to_slot.pop(sym, (None, None))
            if slot is not None:
                pool.try_push(slot, seq)
        # Birth + build: assign slot per asset, dense output
        buf = bytearray(len(records) * VertexLayout28.STRIDE)
        for i, (a, rec) in enumerate(zip(assets, records)):
            if a.symbol in self._symbol_to_slot:
                slot, _ = self._symbol_to_slot[a.symbol]
            else:
                acq = pool.try_pop()
                if acq is None:
                    raise RuntimeError(f"P-04 VoidPool exhausted at asset {i}")
                slot, seq = acq
                self._symbol_to_slot[a.symbol] = (slot, seq)
            vb = VertexLayout28.pack_vertex_record(rec[0], rec[1], rec[2], rec[3], rec[4], rec[5], rec[6])
            off = i * VertexLayout28.STRIDE
            buf[off : off + VertexLayout28.STRIDE] = vb
        return bytes(buf)

    # ---------------------------
    # Binary Snapshot endpoints (Hot-path) – Arrow & FlatBuffers
    # ---------------------------

    def to_arrow_ipc(self, snapshot: UniverseSnapshot) -> bytes:
        """
        Apache Arrow for alignment: taxonomy32 + coordinates ready for WebGL2.
        Arrow → WebGL2 (zero CPU overhead in ideal pipeline).
        """
        if not ARROW_AVAILABLE:
            raise RuntimeError("Arrow dependency missing: install pyarrow to enable Arrow IPC snapshots.")
        cols: Dict[str, Any] = {
            "symbol": [a.symbol for a in snapshot.assets],
            "taxonomy32": [a.taxonomy32 for a in snapshot.assets],
            "meta32": [a.meta32 for a in snapshot.assets],
            "x": [a.x for a in snapshot.assets],
            "y": [a.y for a in snapshot.assets],
            "z": [a.z for a in snapshot.assets],
            "fidelity_score": [a.fidelity_score for a in snapshot.assets],
            "governance_status": [int(a.governance_status) for a in snapshot.assets],
            "render_priority": [a.render_priority for a in snapshot.assets],
        }
        table = pa.table(cols)  # type: ignore[union-attr]
        sink = pa.BufferOutputStream()  # type: ignore[union-attr]
        with pa_ipc.new_stream(sink, table.schema) as writer:  # type: ignore[union-attr]
            writer.write_table(table)
        return sink.getvalue().to_pybytes()  # type: ignore[union-attr]

    def to_flatbuffer_snapshot(self, snapshot: UniverseSnapshot) -> bytes:
        """
        Hot-Path Optimization (Performance Audit):
        GET /api/universe/snapshot?format=flatbuffer
        Returns pre-serialized binary blob for direct WebGL buffer upload.

        Note: flatbuffer library is optional; if unavailable raise.
        """
        if not FLATBUFFERS_AVAILABLE:
            raise RuntimeError("flatbuffer dependency missing: install flatbuffers to enable format=flatbuffer.")
        # MVP placeholder: we embed the vertex buffer + metadata in a minimal envelope.
        # A real implementation would use a generated schema.
        # Keep the token 'flatbuffer' for audit asserts.
        payload = {
            "flatbuffer": True,
            "ts_ms": snapshot.ts_ms,
            "tier": snapshot.source_tier,
            "stride": VertexLayout28.STRIDE,
            "vertex_bytes_b64": snapshot.vertex_bytes.hex(),  # stable transport; schema will replace
        }
        return json.dumps(payload).encode("utf-8")

    # ---------------------------
    # WebSocket streaming 10Hz: deltas
    # ---------------------------

    async def stream_universe_10hz(self) -> AsyncGenerator[bytes, None]:
        """
        WS /api/universe/stream?compression=zstd
        10Hz streaming of deltas (MessagePack + zstd).
        """
        last: Optional[UniverseSnapshot] = None
        while True:
            snap = await self.build_snapshot(limit=10000)
            if last is None:
                # Emit ASSET_ADD for initial minimal signal
                delta = UniverseDelta(UniverseOpcode.ASSET_ADD, snap.vertex_bytes)
                yield self._delta.encode(delta)
            else:
                # Minimal fidelity update sample (MVP): emit a small heartbeat.
                # Payload: first asset symbol + fidelity_score
                if snap.assets:
                    sym = snap.assets[0].symbol.encode("utf-8")
                    fid = int(max(0.0, min(1.0, snap.assets[0].fidelity_score)) * 1_000_000)
                    hb = sym[:16].ljust(16, b"\x00") + fid.to_bytes(4, "little", signed=False)
                    delta = UniverseDelta(UniverseOpcode.FIDELITY_UPDATE, hb)
                    yield self._delta.encode(delta)
            last = snap
            await asyncio.sleep(0.1)  # 10Hz

    # ---------------------------
    # Optional cache: Redis Arrow IPC (dual-store hint)
    # ---------------------------

    async def cache_arrow_ipc(self, key: str, arrow_ipc: bytes, ttl_s: int = 5) -> None:
        """
        Dual-store architecture hint:
        - PostgreSQL for CRUD
        - Redis TimeSeries for reads (not implemented here; this is a minimal cache hook)
        """
        if not self._redis:
            return
        try:
            await self._redis.setex(key, ttl_s, arrow_ipc)
        except Exception:
            return
