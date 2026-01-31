"""
P-04 wire: Build Vertex28 buffer with VoidPool slot allocation.
Birth: acquire slot, write vertex. Death: release slot.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from engines.void_pool import VoidPool

try:
    from backend.models.universe import VertexLayout28
except ImportError:
    VertexLayout28 = None  # type: ignore


STRIDE = 28  # Vertex28


def build_vertex_buffer_with_pool(
    records: List[Tuple[int, int, float, float, float, float, float]],
    pool: VoidPool,
    capacity: Optional[int] = None,
) -> Tuple[bytes, List[Tuple[int, int]]]:
    """
    Build vertex buffer using VoidPool for slot allocation (Birth).
    records: list of (taxonomy32, meta32, x, y, z, fidelity, render_priority)
    pool: primed VoidPool
    Returns (vertex_bytes, [(slot_idx, seq64), ...]) for later release (Death).
    """
    cap = capacity or pool.capacity()
    buf = bytearray(cap * STRIDE)
    slot_seqs: List[Tuple[int, int]] = []
    for rec in records:
        acquired = pool.acquire()
        if acquired is None:
            break
        slot_idx, seq64 = acquired
        off = slot_idx * STRIDE
        if VertexLayout28:
            vb = VertexLayout28.pack_vertex_record(
                rec[0], rec[1], rec[2], rec[3], rec[4], rec[5], rec[6]
            )
        else:
            import struct
            vb = struct.pack("<IIfffff", rec[0] & 0xFFFFFFFF, rec[1] & 0xFFFFFFFF,
                            float(rec[2]), float(rec[3]), float(rec[4]),
                            float(rec[5]), float(rec[6]))
        buf[off : off + STRIDE] = vb
        slot_seqs.append((slot_idx, seq64))
    return bytes(buf[: len(slot_seqs) * STRIDE]), slot_seqs
