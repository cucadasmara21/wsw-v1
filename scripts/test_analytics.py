"""
Quick test script for analytics engine (CUSUM/RLS/VPIN).
Demonstrates signal computation and meta32 packing.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.engine import AnalyticsEngine
from analytics.cusum import CUSUMDetector
from analytics.rls import RLSTrendDetector
from analytics.vpin import VPINCalculator


def test_cusum():
    """Test CUSUM detector."""
    print("=" * 60)
    print("Testing CUSUM Detector")
    print("=" * 60)
    
    detector = CUSUMDetector(threshold=0.02, drift=0.001)
    
    # Simulate price returns
    returns = [0.001, 0.002, 0.001, 0.015, 0.025, 0.001, 0.001]  # Shock at index 3-4
    
    print("Returns sequence:", returns)
    print("\nShock8 scores:")
    for i, ret in enumerate(returns):
        shock8 = detector.update(1, ret)
        print(f"  Step {i+1}: return={ret:.4f}, shock8={shock8}")
    
    print()


def test_rls():
    """Test RLS trend detector."""
    print("=" * 60)
    print("Testing RLS Trend Detector")
    print("=" * 60)
    
    detector = RLSTrendDetector(forgetting_factor=0.95, min_samples=3)
    
    # Simulate price sequence: flat -> bull -> bear
    prices = [100.0, 100.1, 100.2, 100.5, 101.0, 100.8, 100.3, 99.5]
    
    print("Price sequence:", prices)
    print("\nTrend2 scores (0=flat, 1=bull, 2=bear):")
    for i, price in enumerate(prices):
        trend2 = detector.update(1, price)
        trend_name = ["flat", "bull", "bear"][trend2]
        print(f"  Step {i+1}: price={price:.2f}, trend2={trend2} ({trend_name})")
    
    print()


def test_vpin():
    """Test VPIN calculator."""
    print("=" * 60)
    print("Testing VPIN Calculator")
    print("=" * 60)
    
    calculator = VPINCalculator(window_size=5, bucket_count=1)
    
    # Simulate price sequence with volume
    prices = [100.0, 101.0, 102.0, 101.5, 100.5, 99.5, 100.0]
    volumes = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    
    print("Price sequence:", prices)
    print("\nRisk8 and Vital6 scores:")
    prev_price = None
    for i, (price, vol) in enumerate(zip(prices, volumes)):
        risk8, vital6 = calculator.update(1, price, vol, prev_price)
        print(f"  Step {i+1}: price={price:.2f}, risk8={risk8}, vital6={vital6}")
        prev_price = price
    
    print()


def test_engine():
    """Test full analytics engine."""
    print("=" * 60)
    print("Testing Analytics Engine")
    print("=" * 60)
    
    engine = AnalyticsEngine(asset_count=5, macro8=128)
    
    # Initialize assets
    symbols = ["SYNT-000000", "SYNT-000001", "SYNT-000002", "SYNT-000003", "SYNT-000004"]
    index_map = {symbol: i for i, symbol in enumerate(symbols)}
    
    # Initialize with initial prices
    initial_prices = {"SYNT-000000": 100.0, "SYNT-000001": 50.0, "SYNT-000002": 200.0, 
                      "SYNT-000003": 75.0, "SYNT-000004": 150.0}
    
    for symbol, price in initial_prices.items():
        idx = index_map[symbol]
        engine.initialize_asset(idx, idx, price)
    
    print("Initialized 5 assets")
    print("\nSimulating price updates...")
    
    # Simulate 3 ticks
    for tick in range(3):
        # Generate price updates (small variations)
        import random
        prices = {}
        for symbol in symbols:
            base = initial_prices.get(symbol, 100.0)
            # Add small random walk
            change = random.uniform(-0.02, 0.02)
            prices[symbol] = base * (1.0 + change)
        
        # Update engine
        updated = engine.tick(prices, index_map)
        
        print(f"\nTick {tick + 1}: Updated {len(updated)} assets")
        print("Signals for first asset (SYNT-000000):")
        shock, risk, trend, vital, macro = engine.get_signals(0)
        trend_name = ["flat", "bull", "bear"][trend]
        print(f"  shock8={shock}, risk8={risk}, trend2={trend} ({trend_name}), vital6={vital}, macro8={macro}")
        print(f"  meta32=0x{engine.get_meta32(0):08X}")
        
        # Update initial prices for next tick
        initial_prices.update(prices)
    
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Analytics Engine Test Suite")
    print("=" * 60 + "\n")
    
    test_cusum()
    test_rls()
    test_vpin()
    test_engine()
    
    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)
