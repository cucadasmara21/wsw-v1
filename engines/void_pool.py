"""
P-04: ABA-safe slot recycling via MPMC ring buffer with per-cell seq64.
Death→Pool first, then Pool→Birth. Only indices/offsets, no pointers.

SCAFFOLD: This module is a deterministic single-thread reference implementation.
- Python has no shared-memory atomics; this is NOT lock-free MPMC.
- TODO: Replace with native (C++/Rust/WASM + Atomics) for true MPMC correctness.
- Interface is designed for drop-in swap when native path exists.
"""
from __future__ import annotations

import array
from typing import Optional, Tuple

# Per-cell 64-bit sequence tag for ABA immunity
SEQ64_MASK = (1 << 64) - 1

# VOID_READY: slot is in pool (seq=0)
VOID_READY = 0


def _next_pow2(n: int) -> int:
    """Smallest power-of-two >= n."""
    if n <= 1:
        return 1
    n -= 1
    n |= n >> 1
    n |= n >> 2
    n |= n >> 4
    n |= n >> 8
    n |= n >> 16
    return n + 1


class VoidPool:
    """
    Ring buffer with per-cell seq64 (ABA-safe when used correctly).
    Cell layout: seq64 | slot (implicit). Power-of-two capacity.
    SCAFFOLD: Single-thread deterministic; NOT lock-free MPMC (no real atomics).
    """

    def __init__(self, capacity: int):
        if capacity <= 0 or capacity > 1 << 24:
            raise ValueError("capacity must be in [1, 2^24]")
        self._cap = _next_pow2(max(capacity, 2))
        self._mask = self._cap - 1
        # Ring of free slot indices
        self._ring: array.array = array.array("I", [0] * self._cap)
        # Per-slot seq64: 0=in pool, >0=allocated (ABA guard)
        self._slot_seq: array.array = array.array("Q", [VOID_READY] * self._cap)
        self._head: int = 0   # next write
        self._tail: int = 0   # next read
        self._count: int = 0  # free slots in ring
        self._seq: int = 1    # monotonic for new allocations

    def capacity(self) -> int:
        return self._cap

    def mask(self) -> int:
        return self._mask

    def free_count(self) -> int:
        """Number of slots available for acquire."""
        return self._count

    def acquire(self) -> Optional[Tuple[int, int]]:
        """
        Allocate slot from pool (Birth).
        Returns (slot_idx, seq64) or None if pool empty.
        """
        if self._count == 0:
            return None
        slot_idx = self._ring[self._tail]
        self._tail = (self._tail + 1) & self._mask
        self._count -= 1
        self._seq = (self._seq + 1) & SEQ64_MASK
        if self._seq == VOID_READY:
            self._seq = 1
        self._slot_seq[slot_idx] = self._seq
        return (slot_idx, self._seq)

    def release(self, slot_idx: int, seq64: int) -> bool:
        """
        Return slot to pool (Death). Validates seq64 for ABA.
        Returns True if accepted.
        """
        if slot_idx < 0 or slot_idx >= self._cap:
            return False
        if seq64 == VOID_READY:
            return False
        if self._slot_seq[slot_idx] != seq64:
            return False  # ABA: slot was reused
        if self._count >= self._cap:
            return False  # Ring full (invariant violation)
        self._slot_seq[slot_idx] = VOID_READY
        self._ring[self._head] = slot_idx
        self._head = (self._head + 1) & self._mask
        self._count += 1
        return True

    def prime(self, count: Optional[int] = None) -> int:
        """
        Prime pool with free slots (slot_idx 0..count-1).
        Only valid when pool is empty. Returns number primed.
        """
        if self._count != 0:
            return 0
        n = min(count if count is not None else self._cap, self._cap)
        for i in range(n):
            self._slot_seq[i] = VOID_READY
            self._ring[self._head] = i
            self._head = (self._head + 1) & self._mask
            self._count += 1
        return self._count

    def try_pop(self) -> Optional[Tuple[int, int]]:
        """MPMC interface: pop slot for Birth. Returns (slot_idx, seq64) or None."""
        return self.acquire()

    def try_push(self, slot_idx: int, seq64: int) -> bool:
        """MPMC interface: push slot for Death (ABA-safe). Returns True if accepted."""
        return self.release(slot_idx, seq64)
