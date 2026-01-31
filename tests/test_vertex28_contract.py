import struct

from services.vertex28 import OFFSETS, VERTEX28_STRIDE, pack_vertex28, unpack_vertex28, validate_vertex28_blob


def test_vertex28_stride_is_28() -> None:
    assert struct.calcsize("<IIfffff") == 28
    assert VERTEX28_STRIDE == 28


def test_vertex28_offsets_match_frontend_contract() -> None:
    assert OFFSETS["morton_code_u32"] == 0
    assert OFFSETS["meta32_u32"] == 4
    assert OFFSETS["x"] == 8
    assert OFFSETS["y"] == 12
    assert OFFSETS["z"] == 16
    assert OFFSETS["risk"] == 20
    assert OFFSETS["shock"] == 24


def test_vertex28_pack_unpack_roundtrip() -> None:
    b = pack_vertex28(
        morton_code_u32=0xAABBCCDD,
        meta32_u32=0x11223344,
        x=0.1,
        y=0.2,
        z=0.3,
        risk=0.9,
        shock=0.5,
    )
    assert len(b) == 28
    t = unpack_vertex28(b)
    assert t[0] == 0xAABBCCDD
    assert t[1] == 0x11223344
    assert abs(t[2] - 0.1) < 1e-6
    assert abs(t[3] - 0.2) < 1e-6
    assert abs(t[4] - 0.3) < 1e-6
    assert abs(t[5] - 0.9) < 1e-6
    assert abs(t[6] - 0.5) < 1e-6


def test_vertex28_blob_validation() -> None:
    rec = pack_vertex28(1, 2, 0.0, 0.0, 0.0, 1.0, 0.0)
    blob = rec * 10
    assert validate_vertex28_blob(blob) == 10

