"""
Analytics engine for real-time signal injection (CUSUM/RLS/VPIN).
Signals are encoded into meta32 bitfields without changing binary contract.
"""

from .engine import AnalyticsEngine
from .cusum import CUSUMDetector
from .rls import RLSTrendDetector
from .vpin import VPINCalculator

__all__ = ['AnalyticsEngine', 'CUSUMDetector', 'RLSTrendDetector', 'VPINCalculator']
