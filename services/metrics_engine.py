from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Tuple
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import desc

from models import Asset, Price, MetricSnapshot


class AssetType(Enum):
    EQUITY = "equity"
    CRYPTO = "crypto"
    FX = "fx"
    BOND = "bond"
    COMMODITY = "commodity"


@dataclass
class MetricSpec:
    id: str
    name: str
    description: str
    requires: List[str]  # e.g., ["close"]
    frequency: str       # e.g., "1d"
    weight: float        # contribution weight in total score

    def normalize(self, raw: float) -> float:
        # Simple normalizers per metric id
        if self.id == "sma_20":
            return 1.0  # SMA itself not directly scored
        if self.id == "rsi_14":
            # Map RSI 0..100 → risk 0..1 (higher RSI → higher risk)
            return max(0.0, min(1.0, raw / 100.0))
        if self.id == "volatility_20d":
            # Vol as fraction (e.g., 0.02) → scale 0..1 capped
            return max(0.0, min(1.0, raw * 10))
        if self.id == "max_drawdown_90d":
            # Drawdown negative fraction → risk magnitude
            return max(0.0, min(1.0, abs(raw)))
        if self.id == "momentum_30d":
            # Momentum fractional return; negative momentum increases risk
            return max(0.0, min(1.0, max(0.0, -raw)))
        return 0.0


# Registry of metrics for EQUITY (others can share for now)
REGISTRY: List[MetricSpec] = [
    MetricSpec("sma_20", "SMA 20", "20-day simple moving average", ["close"], "1d", weight=0.00),
    MetricSpec("rsi_14", "RSI 14", "14-day relative strength index", ["close"], "1d", weight=0.25),
    MetricSpec("volatility_20d", "Vol 20d", "Std dev of daily returns (20d)", ["close"], "1d", weight=0.25),
    MetricSpec("max_drawdown_90d", "Max DD 90d", "Max drawdown over last 90 days", ["close"], "1d", weight=0.30),
    MetricSpec("momentum_30d", "Momentum 30d", "30-day momentum", ["close"], "1d", weight=0.20),
]


def _fetch_closes(db: Session, asset_id: int, days: int) -> List[Tuple[datetime, float]]:
    rows = (
        db.query(Price.time, Price.close)
        .filter(Price.asset_id == asset_id)
        .order_by(desc(Price.time))
        .limit(days + 100)  # buffer
        .all()
    )
    # return ascending by time for computations
    return list(reversed([(t, c) for (t, c) in rows if c is not None]))


def _sma(values: List[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / float(window)


def _rsi(values: List[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(-period, 0):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains.append(change)
        else:
            losses.append(-change)
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 * (1.0 - (1.0 / (1.0 + rs)))


def _returns(values: List[float]) -> List[float]:
    res = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        curr = values[i]
        if prev:
            res.append((curr - prev) / prev)
    return res


def _volatility(values: List[float], window: int = 20) -> float | None:
    if len(values) < window + 1:
        return None
    rets = _returns(values[-(window + 1):])
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / len(rets)
    return var ** 0.5


def _max_drawdown(values: List[float], window: int = 90) -> float | None:
    if len(values) < window:
        return None
    arr = values[-window:]
    peak = arr[0]
    max_dd = 0.0
    for v in arr:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak else 0.0
        if dd < max_dd:
            max_dd = dd
    return max_dd  # negative fraction


def _momentum(values: List[float], window: int = 30) -> float | None:
    if len(values) < window + 1:
        return None
    past = values[-(window + 1)]
    curr = values[-1]
    return (curr - past) / past if past else None


def detect_asset_type(asset: Asset) -> AssetType:
    # Minimal heuristic; can improve via category
    return AssetType.EQUITY


def compute_metrics_for_asset(db: Session, asset: Asset) -> Dict[str, Any]:
    closes_series = _fetch_closes(db, asset.id, days=120)
    closes = [c for _, c in closes_series]

    metrics: Dict[str, Any] = {}
    # Calculate all supported metrics
    metrics["sma_20"] = _sma(closes, 20)
    metrics["rsi_14"] = _rsi(closes, 14)
    metrics["volatility_20d"] = _volatility(closes, 20)
    metrics["max_drawdown_90d"] = _max_drawdown(closes, 90)
    metrics["momentum_30d"] = _momentum(closes, 30)

    # Derive a simple total score (0..1) via weighted normalized components
    explain_items = []
    total = 0.0
    for spec in REGISTRY:
        raw = metrics.get(spec.id)
        if raw is None:
            continue
        norm = spec.normalize(float(raw))
        contrib = norm * spec.weight
        explain_items.append({
            "metric_id": spec.id,
            "raw_value": raw,
            "normalized_score": norm,
            "weight": spec.weight,
            "contribution": contrib,
        })
        total += contrib

    # Quality flags
    quality = {
        "bars_count": len(closes),
        "low_data": len(closes) < 60,
    }

    return {
        "metrics": metrics,
        "score": total,
        "quality": quality,
        "explain": {"items": explain_items},
        "as_of": closes_series[-1][0] if closes_series else datetime.utcnow(),
    }


def save_snapshot(db: Session, asset_id: int, result: Dict[str, Any]) -> MetricSnapshot:
    snap = MetricSnapshot(
        asset_id=asset_id,
        as_of=result["as_of"],
        metrics=result["metrics"],
        score=result["score"],
        explain=result["explain"],
        created_at=datetime.utcnow(),
    )
    db.add(snap)
    db.commit()
    db.refresh(snap)
    return snap


def latest_snapshot(db: Session, asset_id: int) -> MetricSnapshot | None:
    return (
        db.query(MetricSnapshot)
        .filter(MetricSnapshot.asset_id == asset_id)
        .order_by(MetricSnapshot.as_of.desc())
        .first()
    )


def leaderboard(db: Session, category_id: int | None = None, limit: int = 10) -> List[Dict[str, Any]]:
    # Latest snapshot per asset, ordered by score desc
    query = db.query(MetricSnapshot).order_by(MetricSnapshot.score.desc())
    if category_id:
        # join assets to filter; simple approach
        query = query.join(Asset, MetricSnapshot.asset_id == Asset.id).filter(Asset.category_id == category_id)
    rows = query.limit(limit).all()
    # include symbol/name
    items = []
    for r in rows:
        asset = db.query(Asset).filter(Asset.id == r.asset_id).first()
        if not asset:
            continue
        items.append({
            "asset_id": r.asset_id,
            "symbol": asset.symbol,
            "name": asset.name,
            "score": r.score,
        })
    return items
