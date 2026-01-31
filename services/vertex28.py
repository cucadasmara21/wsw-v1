"""
Vertex28 binary contract (TITAN V8).

Non-negotiable:
- Little-endian pack format: <IIfffff
- Stride: EXACTLY 28 bytes per record
- Offsets (bytes):
  morton_code_u32 @ 0
  meta32_u32      @ 4
  x          @ 8
  y          @ 12
  z          @ 16
  risk       @ 20
  shock      @ 24
"""

from __future__ import annotations

import struct
from typing import Final, Tuple

VERTEX28_STRIDE: Final[int] = 28

OFFSETS: Final[dict[str, int]] = {
    "morton_code_u32": 0,
    "meta32_u32": 4,
    "x": 8,
    "y": 12,
    "z": 16,
    "risk": 20,
    "shock": 24,
}

VERTEX28_STRUCT: Final[struct.Struct] = struct.Struct("<IIfffff")

assert VERTEX28_STRUCT.size == VERTEX28_STRIDE, "Vertex28 struct size must be 28 bytes"


def pack_vertex28(
    morton_code_u32: int,
    meta32_u32: int,
    x: float,
    y: float,
    z: float,
    risk: float,
    shock: float,
) -> bytes:
    """
    Pack a single Vertex28 record.
    """
    b = VERTEX28_STRUCT.pack(
        int(morton_code_u32) & 0xFFFFFFFF,
        int(meta32_u32) & 0xFFFFFFFF,
        float(x),
        float(y),
        float(z),
        float(risk),
        float(shock),
    )
    if len(b) != VERTEX28_STRIDE:
        raise ValueError("FAIL_FAST: VERTEX28_LAYOUT_VIOLATION")
    return b


def unpack_vertex28(buf: bytes) -> Tuple[int, int, float, float, float, float, float]:
    """
    Unpack a single Vertex28 record.
    """
    if len(buf) != VERTEX28_STRIDE:
        raise ValueError("FAIL_FAST: VERTEX28_LAYOUT_VIOLATION")
    morton_u32, meta32, x, y, z, risk, shock = VERTEX28_STRUCT.unpack(buf)
    return int(morton_u32), int(meta32), float(x), float(y), float(z), float(risk), float(shock)


def validate_vertex28_blob(blob: bytes) -> int:
    """
    Validate a concatenated Vertex28 blob and return record count.
    Fail-fast on layout violation (Law III: stride 28 exact).
    """
    n = len(blob)
    if n == 0:
        return 0
    if (n % VERTEX28_STRIDE) != 0:
        raise ValueError("FAIL_FAST: VERTEX28_LAYOUT_VIOLATION")
    return n // VERTEX28_STRIDE

