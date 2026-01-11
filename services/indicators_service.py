"""Indicator computations in pure Python (SMA, RSI, returns, risk)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Sequence

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import IndicatorSnapshot

MIN_BARS_FOR_INDICATORS = 20
RET_N = 20


def _ensure_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _ensure_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def sma(values: Sequence[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def pct_returns(values: Sequence[float]) -> List[float]:
    returns: List[float] = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        curr = values[i]
        if prev == 0:
            returns.append(0.0)
        else:
            returns.append((curr / prev) - 1)
    return returns


def volatility(returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return variance ** 0.5


def max_drawdown(values: Sequence[float]) -> float | None:
    if not values:
        return None
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def compute_risk_components(last_price: float, sma_20_val: float | None, rsi_14_val: float | None, vol_val: float | None, max_dd: float | None, last_return: float | None) -> Dict[str, float]:
    components: Dict[str, float] = {}

    distance = abs(last_price - sma_20_val) / sma_20_val if sma_20_val else 0.0
    components["distance_from_sma"] = clamp(distance * 100, 0, 20)

    rsi_component = 0.0
    if rsi_14_val is not None:
        if rsi_14_val > 70:
            rsi_component = clamp((rsi_14_val - 70) * 0.8, 0, 15)
        elif rsi_14_val < 30:
            rsi_component = clamp((30 - rsi_14_val) * 0.4, 0, 10)
    components["rsi"] = rsi_component

    vol_component = 0.0
    if vol_val is not None:
        vol_component = clamp(vol_val * 4000, 0, 25)  # ~1% daily vol -> 10 points
    components["volatility"] = vol_component

    dd_component = clamp((max_dd or 0.0) * 100, 0, 30)
    components["drawdown"] = dd_component

    momentum_component = 0.0
    if last_return is not None:
        if last_return < 0:
            momentum_component = clamp(abs(last_return) * 100, 0, 10)
        else:
            momentum_component = -clamp(last_return * 100, 0, 5)
    components["momentum"] = momentum_component

    return components


def compute_snapshot(symbol: str, bars: List[Dict[str, Any]], timeframe: str = "1d") -> Dict[str, Any]:
    if not bars:
        raise HTTPException(status_code=404, detail="No bars available for snapshot computation")

    normalized: List[Dict[str, Any]] = []
    for bar in bars:
        ts = _ensure_datetime(bar.get("ts") or bar.get("time"))
        close = _ensure_float(bar.get("close"))
        if ts is None or close is None:
            continue
        normalized.append({
            "ts": ts,
            "open": _ensure_float(bar.get("open")),
            "high": _ensure_float(bar.get("high")),
            "low": _ensure_float(bar.get("low")),
            "close": close,
            "volume": bar.get("volume"),
            "source": bar.get("source"),
        })

    normalized.sort(key=lambda b: b["ts"])
    closes = [b["close"] for b in normalized if b.get("close") is not None]

    if len(closes) < MIN_BARS_FOR_INDICATORS:
        raise HTTPException(status_code=422, detail=f"Not enough data to compute indicators (need {MIN_BARS_FOR_INDICATORS} bars)")

    last_price = closes[-1]
    sma_20_val = sma(closes, 20)
    rsi_14_val = rsi(closes, 14)
    returns_series = pct_returns(closes)
    vol_val = volatility(returns_series)
    max_dd_val = max_drawdown(closes)

    returns_1 = returns_series[-1] if returns_series else None
    returns_n = None
    if len(closes) > RET_N:
        prev = closes[-RET_N - 1]
        if prev != 0:
            returns_n = (last_price / prev) - 1

    risk_components = compute_risk_components(last_price, sma_20_val, rsi_14_val, vol_val, max_dd_val, returns_1)
    risk_score = clamp(50 + sum(risk_components.values()), 0, 100)

    snapshot = {
        "symbol": symbol,
        "timeframe": timeframe,
        "last_price": last_price,
        "timestamp": normalized[-1]["ts"].isoformat(),
        "indicators": {
            "sma20": sma_20_val,
            "rsi14": rsi_14_val,
            "volatility": vol_val,
            "drawdown": max_dd_val,
            "returns_1": returns_1,
            "returns_n": returns_n,
        },
        "risk": {
            "score_total_0_100": risk_score,
            "components": risk_components,
        },
    }
    return snapshot


def persist_snapshot(db: Session, snapshot: Dict[str, Any]) -> IndicatorSnapshot:
    symbol = snapshot.get("symbol")
    timeframe = snapshot.get("timeframe") or "1d"
    ts_val = _ensure_datetime(snapshot.get("timestamp"))
    if ts_val is None:
        raise HTTPException(status_code=400, detail="Invalid snapshot timestamp")

    indicators = snapshot.get("indicators") or {}
    risk = snapshot.get("risk") or {}

    existing = db.query(IndicatorSnapshot).filter(
        IndicatorSnapshot.symbol == symbol,
        IndicatorSnapshot.timeframe == timeframe,
        IndicatorSnapshot.ts == ts_val,
    ).first()
    if existing:
        existing.sma_20 = indicators.get("sma20")
        existing.rsi_14 = indicators.get("rsi14")
        existing.risk_v0 = risk.get("score_total_0_100")
        existing.explain_json = risk.get("components")
        existing.snapshot_json = snapshot
        db.commit()
        db.refresh(existing)
        return existing

    db_obj = IndicatorSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        ts=ts_val,
        sma_20=indicators.get("sma20"),
        rsi_14=indicators.get("rsi14"),
        risk_v0=risk.get("score_total_0_100"),
        explain_json=risk.get("components"),
        snapshot_json=snapshot,
    )
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj
