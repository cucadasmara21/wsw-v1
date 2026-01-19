"""
Canonical 32-bit Taxonomy Bitmask Encoder (Python Truth)
Contract: [3-bit Domain | 1-bit Outlier | 16-bit Risk Score | 12-bit Reserved]

This is the SINGLE SOURCE OF TRUTH for bitmask encoding.
All other implementations (TypeScript, GLSL) must match this exactly.
"""
import numpy as np
from typing import Tuple


def pack_taxonomy_mask(domain: int, outlier: int, risk01: float) -> np.uint32:
    """
    Pack taxonomy components into a 32-bit unsigned integer.
    
    Args:
        domain: 0-5 (3-bit ordinal, "Rule of Six Domains")
        outlier: 0 or 1 (1-bit flag)
        risk01: 0.0-1.0 (normalized risk score)
    
    Returns:
        32-bit unsigned integer bitmask
    
    Contract:
        - domain   = bits 0..2    (mask: 0x7)
        - outlier  = bit 3         (mask: 0x1)
        - risk16   = bits 4..19    (mask: 0xFFFF)
        - reserved = bits 20..31   (mask: 0xFFF)
    
    Packing formula:
        mask = (domain & 0x7) | ((outlier & 0x1) << 3) | ((risk16 & 0xFFFF) << 4)
    """
    # Validate inputs
    if not (0 <= domain <= 5):
        raise ValueError(f"Domain must be 0-5, got {domain}")
    if outlier not in (0, 1):
        raise ValueError(f"Outlier must be 0 or 1, got {outlier}")
    
    # Validate risk01 is numeric and finite (raise on NaN/inf)
    if not np.isfinite(risk01):
        raise ValueError(f"Risk01 must be finite, got {risk01}")
    
    # Clamp finite values to [0,1] then convert to 16-bit integer
    risk01_clamped = np.clip(float(risk01), 0.0, 1.0)
    risk16 = int(np.clip(np.round(risk01_clamped * 65535.0), 0, 65535))
    
    # Pack according to contract
    mask = (
        (domain & 0x7) |                    # bits 0-2: domain
        ((outlier & 0x1) << 3) |            # bit 3: outlier
        ((risk16 & 0xFFFF) << 4)            # bits 4-19: risk score
    )
    
    return np.uint32(mask)


def unpack_taxonomy_mask(mask: np.uint32) -> Tuple[int, int, float]:
    """
    Unpack a 32-bit bitmask into taxonomy components.
    
    Args:
        mask: 32-bit unsigned integer bitmask
    
    Returns:
        Tuple of (domain, outlier, risk01)
    
    Unpacking formula:
        domain   = mask & 0x7
        outlier   = (mask >> 3) & 0x1
        risk16    = (mask >> 4) & 0xFFFF
        risk01    = risk16 / 65535.0
    """
    domain = int(mask & 0x7)
    outlier = int((mask >> 3) & 0x1)
    risk16 = int((mask >> 4) & 0xFFFF)
    risk01 = risk16 / 65535.0
    
    return (domain, outlier, risk01)


def pack_batch(domains: np.ndarray, outliers: np.ndarray, risks01: np.ndarray) -> np.ndarray:
    """
    Vectorized batch packing.
    
    Args:
        domains: (N,) array of domain IDs (0-5)
        outliers: (N,) array of outlier flags (0 or 1)
        risks01: (N,) array of normalized risk scores (0.0-1.0)
    
    Returns:
        (N,) array of uint32 bitmasks
    """
    # Validate shapes
    n = len(domains)
    if len(outliers) != n or len(risks01) != n:
        raise ValueError("All input arrays must have the same length")
    
    # Replace NaN/inf with finite values, then clamp to [0,1] and round to 16-bit
    risks01_clean = np.nan_to_num(risks01, nan=0.0, posinf=1.0, neginf=0.0)
    risks01_clamped = np.clip(risks01_clean, 0.0, 1.0)
    risks16 = np.clip(np.round(risks01_clamped * 65535.0), 0, 65535).astype(np.uint16)
    
    # Pack vectorized
    masks = (
        (domains.astype(np.uint32) & 0x7) |
        ((outliers.astype(np.uint32) & 0x1) << 3) |
        ((risks16.astype(np.uint32) & 0xFFFF) << 4)
    )
    
    return masks.astype(np.uint32)
