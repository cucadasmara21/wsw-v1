"""
Vertex28 binary contract (TITAN V8).

Non-negotiable:
- Little-endian pack format: <IIfffff
- Stride: EXACTLY 28 bytes per record
- Offsets (bytes):
  taxonomy32 @ 0
  meta32     @ 4
  x          @ 8
  y          @ 12
  z          @ 16
  fidelity   @ 20
  spin       @ 24
"""

from __future__ import annotations

import struct
from typing import Final, Tuple

VERTEX28_STRIDE: Final[int] = 28

OFFSETS: Final[dict[str, int]] = {
    "taxonomy32": 0,
    "meta32": 4,
    "x": 8,
    "y": 12,
    "z": 16,
    "fidelity": 20,
    "spin": 24,
}

VERTEX28_STRUCT: Final[struct.Struct] = struct.Struct("<IIfffff")

assert VERTEX28_STRUCT.size == VERTEX28_STRIDE, "Vertex28 struct size must be 28 bytes"


def pack_vertex28(
    taxonomy32: int,
    meta32: int,
    x: float,
    y: float,
    z: float,
    fidelity: float,
    spin: float,
) -> bytes:
    """
    Pack a single Vertex28 record.
    """
    b = VERTEX28_STRUCT.pack(
        int(taxonomy32) & 0xFFFFFFFF,
        int(meta32) & 0xFFFFFFFF,
        float(x),
        float(y),
        float(z),
        float(fidelity),
        float(spin),
    )
    if len(b) != VERTEX28_STRIDE:
        raise ValueError(f"Vertex28 stride violation: got {len(b)} bytes, expected {VERTEX28_STRIDE}")
    return b


def unpack_vertex28(buf: bytes) -> Tuple[int, int, float, float, float, float, float]:
    """
    Unpack a single Vertex28 record.
    """
    if len(buf) != VERTEX28_STRIDE:
        raise ValueError(f"Vertex28 stride violation: got {len(buf)} bytes, expected {VERTEX28_STRIDE}")
    taxonomy32, meta32, x, y, z, fidelity, spin = VERTEX28_STRUCT.unpack(buf)
    return int(taxonomy32), int(meta32), float(x), float(y), float(z), float(fidelity), float(spin)


def validate_vertex28_blob(blob: bytes) -> int:
    """
    Validate a concatenated Vertex28 blob and return record count.
    """
    n = len(blob)
    if n == 0:
        return 0
    if (n % VERTEX28_STRIDE) != 0:
        raise ValueError(f"Vertex28 blob length {n} is not a multiple of {VERTEX28_STRIDE}")
    return n // VERTEX28_STRIDE

