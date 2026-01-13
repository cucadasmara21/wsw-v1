"""
Tests for Risk Engine v1 (services/risk_service.py and api/risk.py endpoints)
"""

import pytest
import numpy as np
from services.risk_service import compute_risk_vector, compute_cri


def test_compute_risk_vector_empty():
    """Test with empty prices list."""
    vector = compute_risk_vector([])
    assert vector["insufficient_data"] == True
    assert vector["volatility"] == 0.0
    assert vector["max_drawdown"] == 0.0


def test_compute_risk_vector_single_price():
    """Test with single price (insufficient)."""
    vector = compute_risk_vector([100.0])
    assert vector["insufficient_data"] == True


def test_compute_risk_vector_two_prices():
    """Test with two prices (minimal data)."""
    prices = [100.0, 101.0]
    vector = compute_risk_vector(prices)
    assert vector["insufficient_data"] == False
    assert 0.0 <= vector["volatility"] <= 1.0
    assert 0.0 <= vector["max_drawdown"] <= 1.0


def test_compute_risk_vector_stable_prices():
    """Test with stable (flat) prices."""
    prices = [100.0] * 100
    vector = compute_risk_vector(prices)
    assert vector["insufficient_data"] == False
    assert vector["volatility"] < 0.01  # Very low volatility
    assert vector["max_drawdown"] == 0.0  # No drawdown


def test_compute_risk_vector_volatile_prices():
    """Test with volatile prices."""
    # Simulate high volatility: strong oscillations
    prices = []
    for i in range(100):
        if i % 2 == 0:
            prices.append(100.0)
        else:
            prices.append(110.0)
    
    vector = compute_risk_vector(prices)
    assert vector["insufficient_data"] == False
    assert vector["volatility"] > 0.1  # Significant volatility


def test_compute_risk_vector_drawdown():
    """Test max drawdown computation."""
    # Prices: steady rise then crash
    prices = list(range(100, 150)) + list(range(149, 70, -1))
    vector = compute_risk_vector(prices)
    assert vector["insufficient_data"] == False
    assert vector["max_drawdown"] > 0.3  # At least 30% drawdown
    assert vector["max_drawdown"] <= 1.0


def test_compute_risk_vector_all_ranges():
    """Test that all components are in valid ranges."""
    prices = [100.0 * np.sin(i / 10) + 100 for i in range(100)]
    volumes = [1e6 for _ in range(100)]
    
    vector = compute_risk_vector(prices, volumes)
    
    assert 0.0 <= vector["volatility"] <= 1.0
    assert 0.0 <= vector["max_drawdown"] <= 1.0
    assert 0.0 <= vector["momentum_30d"] <= 1.0
    assert 0.0 <= vector["liquidity"] <= 1.0
    assert 0.0 <= vector["centrality"] <= 1.0


def test_compute_cri_null_when_insufficient():
    """Test that CRI is None when insufficient data."""
    vector = {"insufficient_data": True}
    cri = compute_cri(vector)
    assert cri is None


def test_compute_cri_range():
    """Test that CRI is always in 0..100."""
    for _ in range(10):
        vector = {
            "volatility": np.random.random(),
            "max_drawdown": np.random.random(),
            "momentum_30d": np.random.random(),
            "liquidity": np.random.random(),
            "centrality": np.random.random(),
            "insufficient_data": False,
        }
        cri = compute_cri(vector)
        assert cri is not None
        assert 0.0 <= cri <= 100.0


def test_compute_cri_deterministic():
    """Test that CRI computation is deterministic."""
    vector = {
        "volatility": 0.3,
        "max_drawdown": 0.2,
        "momentum_30d": 0.5,
        "liquidity": 0.8,
        "centrality": 0.5,
        "insufficient_data": False,
    }
    
    cri1 = compute_cri(vector)
    cri2 = compute_cri(vector)
    assert cri1 == cri2


def test_compute_cri_expected_formula():
    """Test CRI formula with known values."""
    # All components = 0 => CRI should be ~0
    vector_low = {
        "volatility": 0.0,
        "max_drawdown": 0.0,
        "momentum_30d": 0.0,
        "liquidity": 1.0,
        "centrality": 0.0,
        "insufficient_data": False,
    }
    cri_low = compute_cri(vector_low)
    assert cri_low < 10.0
    
    # All components = 1 => CRI should be ~100
    vector_high = {
        "volatility": 1.0,
        "max_drawdown": 1.0,
        "momentum_30d": 1.0,
        "liquidity": 0.0,
        "centrality": 1.0,
        "insufficient_data": False,
    }
    cri_high = compute_cri(vector_high)
    assert cri_high > 90.0
