from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Iterable, List

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.vertex28 import pack_vertex28


def _clamp01(v: float) -> float:
    if v <= 0.0:
        return 0.0
    if v >= 1.0:
        return 1.0
    return v


def stable_f01(symbol: str, salt: str) -> float:
    h = hashlib.sha256((salt + ":" + symbol).encode("utf-8")).digest()
    return (int.from_bytes(h[:4], "big") % 1_000_000) / 1_000_000.0


def morton63_from_unit_xyz(x: float, y: float, z: float) -> int:
    """
    63-bit Morton code: 21 bits per axis, interleaved (x,y,z). Inputs are clamped to [0,1].
    """

    def q21(u: float) -> int:
        u = _clamp01(float(u))
        return int(u * ((1 << 21) - 1)) & 0x1FFFFF

    qx, qy, qz = q21(x), q21(y), q21(z)

    out = 0
    for i in range(21):
        out |= ((qx >> i) & 1) << (3 * i)
        out |= ((qy >> i) & 1) << (3 * i + 1)
        out |= ((qz >> i) & 1) << (3 * i + 2)
    return out & 0x7FFFFFFFFFFFFFFF


def taxonomy32_simple(i: int) -> int:
    # Deterministic, non-zero-ish u32 values.
    return (0xA5A50000 | (i & 0xFFFF)) & 0xFFFFFFFF


def meta32_simple(i: int) -> int:
    # Deterministic meta32 bits expected by legacy shader (shock/risk/trend).
    shock = i % 255
    risk = (i * 7) % 255
    trend = i % 3
    vital = (i * 13) % 63
    macro = (i * 17) % 255
    return (shock & 0xFF) | ((risk & 0xFF) << 8) | ((trend & 0x3) << 16) | ((vital & 0x3F) << 18) | ((macro & 0xFF) << 24)


def iter_synthetic_rows(n: int, *, prefix: str = "SYN") -> Iterable[dict]:
    sectors = ["TECH", "FIN", "HLTH", "ENER", "INDS", "COMM", "MATR", "UTIL"]
    for i in range(int(n)):
        sym = f"{prefix}{i:06d}"
        sector = sectors[i % len(sectors)]
        x = stable_f01(sym, "x")
        y = stable_f01(sym, "y")
        z = stable_f01(sym, "z") * 0.15
        tax32 = taxonomy32_simple(i)
        meta32 = meta32_simple(i)
        fid = 0.92
        spin = float((i % 2))
        mort = morton63_from_unit_xyz(x, y, z)
        vb = pack_vertex28(tax32, meta32, x, y, z, fid, spin)
        yield {
            "asset_id": uuid.uuid4(),
            "symbol": sym,
            "sector": sector,
            "morton_code": int(mort),
            "taxonomy32": int(tax32),
            "meta32": int(meta32),
            "x": float(x),
            "y": float(y),
            "z": float(z),
            "fidelity_score": float(fid),
            "spin": float(spin),
            "vertex_buffer": vb,
        }


def seed_universe_assets_if_empty(engine: Engine, *, min_rows: int = 2000) -> int:
    """
    Idempotent: ensures at least min_rows deterministic SYN* rows exist in public.universe_assets.
    Returns the resulting row count (best-effort).
    """
    try:
        with engine.begin() as conn:
            has_table = bool(conn.execute(text("SELECT to_regclass('public.universe_assets') IS NOT NULL")).scalar())
            if not has_table:
                return 0
            n = int(conn.execute(text("SELECT COUNT(*) FROM public.universe_assets")).scalar() or 0)
            if n >= int(min_rows):
                return n

            rows = list(iter_synthetic_rows(int(min_rows)))
            conn.execute(
                text(
                    """
                    INSERT INTO public.universe_assets (
                      asset_id, symbol, sector, morton_code, taxonomy32, meta32, x, y, z, fidelity_score, spin, vertex_buffer
                    )
                    VALUES (
                      :asset_id, :symbol, :sector, :morton_code, :taxonomy32, :meta32, :x, :y, :z, :fidelity_score, :spin, :vertex_buffer
                    )
                    ON CONFLICT (symbol) DO UPDATE SET
                      sector=EXCLUDED.sector,
                      morton_code=EXCLUDED.morton_code,
                      taxonomy32=EXCLUDED.taxonomy32,
                      meta32=EXCLUDED.meta32,
                      x=EXCLUDED.x, y=EXCLUDED.y, z=EXCLUDED.z,
                      fidelity_score=EXCLUDED.fidelity_score,
                      spin=EXCLUDED.spin,
                      vertex_buffer=EXCLUDED.vertex_buffer,
                      last_quantum_update=NOW();
                    """
                ),
                rows,
            )
            n2 = int(conn.execute(text("SELECT COUNT(*) FROM public.universe_assets")).scalar() or 0)
            return n2
    except Exception:
        return 0

