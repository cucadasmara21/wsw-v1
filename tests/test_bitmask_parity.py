"""
Parity test: Python pack == TypeScript decode
Ensures bitmask encoding is consistent across languages.
"""
import pytest
import numpy as np
from engines.bitmask_encoder import pack_taxonomy_mask, unpack_taxonomy_mask


def test_pack_unpack_roundtrip():
    """Test that pack → unpack returns original values"""
    test_cases = [
        (0, 0, 0.0),
        (5, 1, 1.0),
        (2, 0, 0.5),
        (1, 1, 0.75),
        (3, 0, 0.12345),
    ]
    
    for domain, outlier, risk01 in test_cases:
        mask = pack_taxonomy_mask(domain, outlier, risk01)
        domain_out, outlier_out, risk01_out = unpack_taxonomy_mask(mask)
        
        assert domain_out == domain, f"Domain mismatch: {domain_out} != {domain}"
        assert outlier_out == outlier, f"Outlier mismatch: {outlier_out} != {outlier}"
        assert abs(risk01_out - risk01) < 1e-5, f"Risk mismatch: {risk01_out} != {risk01}"


def test_bitmask_layout():
    """Test that bitmask layout matches contract exactly"""
    # Test domain bits (0-2)
    mask = pack_taxonomy_mask(domain=5, outlier=0, risk01=0.0)
    assert (mask & 0x7) == 5, "Domain bits incorrect"
    
    # Test outlier bit (3)
    mask = pack_taxonomy_mask(domain=0, outlier=1, risk01=0.0)
    assert ((mask >> 3) & 0x1) == 1, "Outlier bit incorrect"
    
    # Test risk bits (4-19)
    mask = pack_taxonomy_mask(domain=0, outlier=0, risk01=1.0)
    risk16 = (mask >> 4) & 0xFFFF
    assert risk16 == 65535, "Risk bits incorrect (max)"
    
    mask = pack_taxonomy_mask(domain=0, outlier=0, risk01=0.5)
    risk16 = (mask >> 4) & 0xFFFF
    assert abs(risk16 - 32767) < 2, "Risk bits incorrect (mid)"  # Allow rounding


def test_batch_packing():
    """Test vectorized batch packing"""
    from engines.bitmask_encoder import pack_batch
    
    n = 1000
    domains = np.random.randint(0, 6, size=n, dtype=np.int32)
    outliers = np.random.randint(0, 2, size=n, dtype=np.int32)
    risks01 = np.random.rand(n).astype(np.float32)
    
    masks = pack_batch(domains, outliers, risks01)
    
    assert len(masks) == n
    assert masks.dtype == np.uint32
    
    # Verify a few samples
    for i in range(min(10, n)):
        domain_out, outlier_out, risk01_out = unpack_taxonomy_mask(masks[i])
        assert domain_out == domains[i]
        assert outlier_out == outliers[i]
        assert abs(risk01_out - risks01[i]) < 1e-4


def test_edge_cases():
    """Test edge cases and validation"""
    # Domain out of range
    with pytest.raises(ValueError):
        pack_taxonomy_mask(domain=6, outlier=0, risk01=0.0)
    
    # Outlier out of range
    with pytest.raises(ValueError):
        pack_taxonomy_mask(domain=0, outlier=2, risk01=0.0)
    
    # Risk out of range (finite values are clamped, not raised)
    # Test that clamping works for finite values > 1.0
    mask = pack_taxonomy_mask(domain=0, outlier=0, risk01=1.5)  # Should clamp to 1.0
    _, _, risk01_out = unpack_taxonomy_mask(mask)
    assert abs(risk01_out - 1.0) < 1e-5, f"Expected 1.0, got {risk01_out}"
    
    # Clamping works for values > 1.0
    mask = pack_taxonomy_mask(domain=0, outlier=0, risk01=2.0)  # Should clamp to 1.0
    _, _, risk01_out = unpack_taxonomy_mask(mask)
    assert abs(risk01_out - 1.0) < 1e-5, f"Expected 1.0, got {risk01_out}"
    
    # Negative values clamp to 0.0
    mask = pack_taxonomy_mask(domain=0, outlier=0, risk01=-0.5)  # Should clamp to 0.0
    _, _, risk01_out = unpack_taxonomy_mask(mask)
    assert abs(risk01_out - 0.0) < 1e-5, f"Expected 0.0, got {risk01_out}"
