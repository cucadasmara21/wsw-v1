"""
Extensible metrics registry for computing asset metrics
Supports core metrics + category-specific overrides
"""
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class MetricsRegistry:
    """
    Registry for computing metrics on assets.
    
    Each compute function returns:
    {
        "metrics": {...},        # computed values
        "quality": {...},        # data quality indicators
        "explain": {...}         # breakdown/explanation
    }
    """
    
    def __init__(self):
        self.core_computer = None
        self.category_computers: Dict[int, Any] = {}  # category_id -> computer
    
    def register_core(self, computer):
        """Register core metrics computer"""
        self.core_computer = computer
        return self
    
    def register_category(self, category_id: int, computer):
        """Register category-specific metrics computer"""
        self.category_computers[category_id] = computer
        return self
    
    def compute(
        self,
        asset,
        bars: List[Dict[str, float]],
        category_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Compute metrics for an asset using available bars.
        
        Args:
            asset: Asset model instance
            bars: List of OHLCV dicts with 'close', 'high', 'low', 'volume' keys
            category_id: Optional category ID for category-specific logic
        
        Returns:
            {
                "metrics": {...},
                "quality": {...},
                "explain": {...}
            }
        """
        if not self.core_computer:
            logger.warning("No core computer registered")
            return {"metrics": {}, "quality": {}, "explain": {}}
        
        # Start with core metrics
        result = self.core_computer.compute(asset, bars)
        
        # Apply category override if available
        if category_id and category_id in self.category_computers:
            cat_result = self.category_computers[category_id].compute(asset, bars)
            # Merge/override
            if cat_result.get("metrics"):
                result["metrics"].update(cat_result["metrics"])
            if cat_result.get("quality"):
                result["quality"].update(cat_result["quality"])
            if cat_result.get("explain"):
                result["explain"].update(cat_result["explain"])
        
        return result


class CoreMetricsComputer:
    """
    Core metrics computer: SMA20, RSI14, volatility, max_drawdown, momentum
    """
    
    @staticmethod
    def compute(asset, bars: List[Dict[str, float]]) -> Dict[str, Any]:
        """Compute core metrics from bars"""
        if not bars:
            return {
                "metrics": {},
                "quality": {"low_data": True, "bars_count": 0},
                "explain": {"error": "No bars available"}
            }
        
        closes = [b.get("close", 0) for b in bars]
        highs = [b.get("high", 0) for b in bars]
        lows = [b.get("low", 0) for b in bars]
        volumes = [b.get("volume", 0) for b in bars]
        
        metrics = {}
        quality = {"bars_count": len(bars), "low_data": len(bars) < 20}
        explain = {}
        
        # SMA20
        if len(closes) >= 20:
            sma20 = sum(closes[-20:]) / 20
            metrics["sma20"] = round(sma20, 2)
        
        # RSI14
        if len(closes) >= 14:
            rsi14 = CoreMetricsComputer._calculate_rsi(closes, 14)
            metrics["rsi14"] = round(rsi14, 2)
        
        # Volatility (std dev of returns)
        if len(closes) >= 2:
            returns = [
                (closes[i] - closes[i-1]) / closes[i-1]
                for i in range(1, len(closes))
            ]
            if returns:
                mean_return = sum(returns) / len(returns)
                variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
                volatility = variance ** 0.5
                metrics["volatility"] = round(volatility, 4)
        
        # Max drawdown
        if len(closes) >= 2:
            cummax = closes[0]
            drawdowns = []
            for close in closes[1:]:
                if close > cummax:
                    cummax = close
                drawdown = (close - cummax) / cummax if cummax != 0 else 0
                drawdowns.append(drawdown)
            if drawdowns:
                max_drawdown = min(drawdowns)
                metrics["max_drawdown"] = round(max_drawdown, 4)
        
        # Momentum (close vs close 10 periods ago)
        if len(closes) >= 10:
            momentum = (closes[-1] - closes[-10]) / closes[-10] if closes[-10] != 0 else 0
            metrics["momentum"] = round(momentum, 4)
        
        # Latest price
        if closes:
            metrics["last_price"] = round(closes[-1], 2)
        
        return {
            "metrics": metrics,
            "quality": quality,
            "explain": explain
        }
    
    @staticmethod
    def _calculate_rsi(closes: List[float], period: int = 14) -> float:
        """Calculate RSI14"""
        if len(closes) < period + 1:
            return 0
        
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [abs(d) if d < 0 else 0 for d in deltas]
        
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100 if avg_gain > 0 else 0
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


# Global registry instance
registry = MetricsRegistry()
registry.register_core(CoreMetricsComputer())
