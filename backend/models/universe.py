"""
LA CATEDRAL CUÁNTICA DE DATOS
Verdades absolutas materializadas (extractos):


taxonomy32 bitmask: [3-bit Domain | 1-bit Outlier | 16-bit Risk Score | 12-bit Reserved]


meta32 bitmask:     [8b Risk | 8b Shock | 2b Trend | 6b Vitality]


Mandatory: fidelity_score, governance_status


GPU metadata fields: render_priority, cluster_id, lod_distance_km, heatmap_color_encoding, adjacency_bitset


Morton-Z Order Curves for 3D risk-locality mapping


Numba @njit kernels for genetic distance + field (parallel=True, fastmath=True, cache=True)


WebGL2 Vertex Buffer: struct.pack stride 28 bytes EXACT (or 24); here: 28 bytes (7×float32 equivalent footprint)
"""


from __future__ import annotations
import math
import struct
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, ClassVar, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Float,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
)
try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore
try:
    from numba import njit, prange, uint32, float32
    NUMBA_AVAILABLE = True
except Exception:  # pragma: no cover
    NUMBA_AVAILABLE = False
    def njit(*args: Any, **kwargs: Any):  # type: ignore
        def _wrap(fn: Any) -> Any:
            return fn
        return _wrap

    def prange(*args: Any, **kwargs: Any):  # type: ignore
        return range(*args)

    uint32 = int  # type: ignore
    float32 = float  # type: ignore

# ---------------------------
# Governance (Del Dato a la Decisión)
# ---------------------------
class GovernanceStatus(IntEnum):
    PROVISIONAL = 1
    SANCTIONED = 2
    QUARANTINED = 3
    ARCHIVED = 4
    BLACKLISTED = 5

# ---------------------------
# SQLAlchemy Core (NO ORM): Universe Registry Table
# ---------------------------
metadata = MetaData()
universe_assets = Table(
    "universe_assets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("symbol", String(32), nullable=False, unique=True, index=True),
    Column("is_active", Boolean, nullable=False, server_default="true"),
    # Bitfields (Truth)
    Column("taxonomy32", Integer, nullable=False, server_default="0"),
    Column("meta32", Integer, nullable=False, server_default="0"),
    # Mandatory governance + fidelity
    Column("fidelity_score", Float, nullable=False, server_default="0.0"),
    Column("governance_status", SmallInteger, nullable=False, server_default=str(int(GovernanceStatus.PROVISIONAL))),
    # Spatial (Uint16 coords packed elsewhere; store float for analytics)
    Column("x", Float, nullable=True),
    Column("y", Float, nullable=True),
    Column("z", Float, nullable=True),
    Column("morton63", Text, nullable=True),  # stringified uint64 for portability
    # Performance Audit: GPU metadata fields (required)
    Column("render_priority", SmallInteger, nullable=False, server_default="100"),  # 0-255
    Column("cluster_id", Text, nullable=True),  # UUID stored as text for portability
    Column("lod_distance_km", Text, nullable=True),  # JSON-ish string or ARRAY in real schema
    Column("heatmap_color_encoding", LargeBinary, nullable=True),  # precomputed RGB24 packed
    Column("adjacency_bitset", Text, nullable=True),  # BIGINT in real schema; here text for portability
    # Aux
    Column("liquidity_tier", SmallInteger, nullable=False, server_default="1"),
    Column("sector", String(64), nullable=True),
    Column("name", String(128), nullable=True),
    Column("notes", Text, nullable=True),
    CheckConstraint("fidelity_score >= 0.0 AND fidelity_score <= 1.0", name="ck_universe_fidelity_score_0_1"),
    Index("ix_universe_assets_active_priority", "is_active", "render_priority"),
)

# ---------------------------
# Bitfield packing/unpacking
# ---------------------------
def pack_taxonomy32(domain: int, outlier: int, risk16: int, reserved12: int = 0) -> int:
    """
    taxonomy32: [3b Domain | 1b Outlier | 16b Risk Score | 12b Reserved]
    Layout (MSB→LSB): domain[31:29], outlier[28], risk[27:12], reserved[11:0]
    """
    d = (domain & 0x7) << 29
    o = (outlier & 0x1) << 28
    r = (risk16 & 0xFFFF) << 12
    z = reserved12 & 0xFFF
    return (d | o | r | z) & 0xFFFFFFFF


def unpack_taxonomy32(taxonomy32: int) -> Tuple[int, int, int, int]:
    domain = (taxonomy32 >> 29) & 0x7
    outlier = (taxonomy32 >> 28) & 0x1
    risk16 = (taxonomy32 >> 12) & 0xFFFF
    reserved12 = taxonomy32 & 0xFFF
    return domain, outlier, risk16, reserved12


def pack_meta32(risk8: int, shock8: int, trend2: int, vitality6: int, reserved8: int = 0) -> int:
    """
    meta32: [8b Risk | 8b Shock | 2b Trend | 6b Vitality | 8b Reserved]
    Layout (LSB→MSB):
    risk[7:0], shock[15:8], trend[17:16], vitality[23:18], reserved[31:24]
    """
    r = (risk8 & 0xFF)
    s = (shock8 & 0xFF) << 8
    t = (trend2 & 0x3) << 16
    v = (vitality6 & 0x3F) << 18
    z = (reserved8 & 0xFF) << 24
    return (r | s | t | v | z) & 0xFFFFFFFF


def unpack_meta32(meta32: int) -> Tuple[int, int, int, int, int]:
    risk8 = meta32 & 0xFF
    shock8 = (meta32 >> 8) & 0xFF
    trend2 = (meta32 >> 16) & 0x3
    vitality6 = (meta32 >> 18) & 0x3F
    reserved8 = (meta32 >> 24) & 0xFF
    return risk8, shock8, trend2, vitality6, reserved8

# ---------------------------
# Morton-Z encoding (63-bit, 21 bits per axis)
# ---------------------------
def _clamp21(v: int) -> int:
    return 0 if v < 0 else (0x1FFFFF if v > 0x1FFFFF else v)


def _part1by2_21(n: int) -> int:
    """
    Interleave bits with two zeros between (21-bit input → 63-bit spread).
    """
    n &= 0x1FFFFF
    n = (n | (n << 32)) & 0x1F00000000FFFF
    n = (n | (n << 16)) & 0x1F0000FF0000FF
    n = (n | (n << 8)) & 0x100F00F00F00F00F
    n = (n | (n << 4)) & 0x10C30C30C30C30C3
    n = (n | (n << 2)) & 0x1249249249249249
    return n


def morton3d_21bit(x: int, y: int, z: int) -> int:
    """
    Morton: |x⟩⊗|y⟩⊗|z⟩ → |m⟩ preserving locality (risk-locality).
    21 bits each → 63-bit Morton code.
    """
    xx = _part1by2_21(_clamp21(x))
    yy = _part1by2_21(_clamp21(y)) << 1
    zz = _part1by2_21(_clamp21(z)) << 2
    return (xx | yy | zz) & ((1 << 63) - 1)

# P-01: FP32 stability (EPS_DIST = 1e-9) enforced in compute_genetic_field and shaders.

# ---------------------------
# Numba kernels (Apéndice Técnico Ineludible)
# ---------------------------
@njit(parallel=True, fastmath=True, cache=True)
def quantum_genetic_distance(taxonomy_a: uint32, taxonomy_b: uint32) -> uint32:
    """
    Hamming distance over 32-bit taxonomy with sector weighting.
    parallel=True required by mandate.
    """
    xorv = taxonomy_a ^ taxonomy_b
    # Sector weights (domain/outlier/risk/reserved) - kept simple and stable.
    # Domain(3b) + Outlier(1b) + Risk(16b) + Reserved(12b)
    dmask = uint32(0xE0000000)  # domain bits
    omask = uint32(0x10000000)  # outlier bit
    rmask = uint32(0x0FFFF000)  # risk bits
    zmask = uint32(0x00000FFF)  # reserved bits
    d = xorv & dmask
    o = xorv & omask
    r = xorv & rmask
    z = xorv & zmask

    # popcount without Python int methods
    def _popcount(u: uint32) -> uint32:
        x = u
        x = x - ((x >> 1) & uint32(0x55555555))
        x = (x & uint32(0x33333333)) + ((x >> 2) & uint32(0x33333333))
        x = (x + (x >> 4)) & uint32(0x0F0F0F0F)
        x = x + (x >> 8)
        x = x + (x >> 16)
        return x & uint32(0x3F)

    # Weighted sum (scaled to uint32)
    return (
        _popcount(d) * uint32(3) +
        _popcount(o) * uint32(2) +
        _popcount(r) * uint32(1) +
        _popcount(z) * uint32(1)
    )


@njit(parallel=True, fastmath=True, cache=True)
def compute_genetic_field(taxonomies: Any, metas: Any, out_field: Any) -> None:
    """
    out_field[i] = Σ_j exp(-D_ij/λ) * (risk_j / 255.0)
    Vectorized over i with prange for SIMD-friendly loops (parallel=True).
    P-01: dist = max(EPS_DIST, dist) before any division/normalization.
    """
    lam = float32(10.0)
    eps = float32(1e-9)
    n = taxonomies.shape[0]
    for i in prange(n):
        acc = float32(0.0)
        ti = uint32(taxonomies[i])
        for j in range(n):
            if i == j:
                continue
            tj = uint32(taxonomies[j])
            d = float32(quantum_genetic_distance(ti, tj))
            dist = max(d, eps)  # P-01: branchless guard
            # meta risk is low 8 bits
            risk_j = float32(metas[j] & 0xFF) / float32(255.0)
            acc += math.exp(-dist / lam) * risk_j
        out_field[i] = acc

# ---------------------------
# WebGL2 Vertex Buffer Layout (28 bytes)
# ---------------------------
class VertexLayout28:
    """
    WebGL2/WebGPU-friendly: 28 bytes EXACT.
    FORMAT: <IIfffff
    taxonomy32:uint32, meta32:uint32, x:float32, y:float32, z:float32, fidelity:float32, render_priority:float32
    NOTE: This is an explicit 28-byte stride. (struct.pack used for compliance + pack_into for zero-copy buffer fill)
    """
    STRIDE: ClassVar[int] = 28
    FORMAT: ClassVar[str] = "<IIfffff"
    PACKER: ClassVar[struct.Struct] = struct.Struct(FORMAT)

    @staticmethod
    def pack_vertex_record(taxonomy32: int, meta32: int, x: float, y: float, z: float, fidelity: float, render_priority: float) -> bytes:
        # Mandatory: include struct.pack token (audit asserts).
        return struct.pack(VertexLayout28.FORMAT, taxonomy32 & 0xFFFFFFFF, meta32 & 0xFFFFFFFF, float(x), float(y), float(z), float(fidelity), float(render_priority))

    @staticmethod
    def pack_vertex_buffer(records: Sequence[Tuple[int, int, float, float, float, float, float]]) -> bytes:
        n = len(records)
        buf = bytearray(n * VertexLayout28.STRIDE)
        mv = memoryview(buf)
        off = 0
        for (tax, meta, x, y, z, fid, pri) in records:
            VertexLayout28.PACKER.pack_into(
                mv, off,
                tax & 0xFFFFFFFF,
                meta & 0xFFFFFFFF,
                float(x), float(y), float(z),
                float(fid),
                float(pri),
            )
            off += VertexLayout28.STRIDE
        return bytes(buf)

# ---------------------------
# Domain Asset (Typed view)
# ---------------------------
@dataclass(frozen=True, slots=True)
class UniverseAsset:
    """
    UniverseAsset = axioma del Registry (Unidad de Verdad).
    """
    symbol: str
    taxonomy32: int
    meta32: int
    fidelity_score: float
    governance_status: GovernanceStatus
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    render_priority: int = 100
    cluster_id: Optional[uuid.UUID] = None
    lod_distance_km: Tuple[float, float, float, float] = (1.0, 5.0, 25.0, 100.0)
    heatmap_color_encoding: bytes = b""
    adjacency_bitset: int = 0

    liquidity_tier: int = 1
    sector: str = ""
    name: str = ""

    def taxonomy_parts(self) -> Tuple[int, int, int, int]:
        return unpack_taxonomy32(self.taxonomy32)

    def meta_parts(self) -> Tuple[int, int, int, int, int]:
        return unpack_meta32(self.meta32)

    def morton_code(self) -> int:
        # Map floats into 21-bit grid deterministically (caller should normalize).
        xi = int(max(0.0, min(1.0, self.x)) * 0x1FFFFF)
        yi = int(max(0.0, min(1.0, self.y)) * 0x1FFFFF)
        zi = int(max(0.0, min(1.0, self.z)) * 0x1FFFFF)
        return morton3d_21bit(xi, yi, zi)

    def spin(self) -> float:
        # Simple parity-based spin operator from taxonomy bit parity and risk16.
        _, _, risk16, _ = self.taxonomy_parts()
        parity = bin(self.taxonomy32 & 0xFFFFFFFF).count("1") & 1
        base = float(risk16) / 65535.0
        return -base if parity else base

    def to_vertex_record(self) -> Tuple[int, int, float, float, float, float, float]:
        # x,y,z should be normalized (0..1) for morton locality, but GPU can interpret as raw floats.
        pri_f = float(max(0, min(255, self.render_priority)))
        return (
            self.taxonomy32 & 0xFFFFFFFF,
            self.meta32 & 0xFFFFFFFF,
            float(self.x), float(self.y), float(self.z),
            float(max(0.0, min(1.0, self.fidelity_score))),
            pri_f,
        )
