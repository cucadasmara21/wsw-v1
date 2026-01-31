#!/usr/bin/env python3
"""
Sanity check: Vertex28 packing produces exactly 28 bytes.
"""
import struct

VERTEX_STRUCT = struct.Struct("<IIfffff")  # taxonomy32, meta32, x, y, z, fidelity, spin

# Test pack
taxonomy32 = 0x12345678
meta32 = 0xABCDEF00
x, y, z = 0.5, 0.25, 0.75
fidelity = 0.92
spin = 0.314

packed = VERTEX_STRUCT.pack(
    taxonomy32 & 0xFFFFFFFF,
    meta32 & 0xFFFFFFFF,
    float(x), float(y), float(z),
    float(fidelity), float(spin)
)

assert len(packed) == 28, f"Vertex28 stride = {len(packed)}, expected 28"
print("OK Vertex28 = 28 bytes")
