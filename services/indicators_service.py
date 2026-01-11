"""Indicators computation service (SMA, RSI, risk_v0)."""
from __future__ import annotations

from typing import List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from fastapi import HTTPException

from models import PriceBar, IndicatorSnapshot


def sma(values: List[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values: List[float], period: int = 14) -> float | None:
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


def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


def compute_risk_v0(latest_close: float, sma_20: float | None, rsi_14: float | None) -> Tuple[float, Dict[str, Any]]:
    """Simple explainable risk score (0-100)."""
    distance = 0.0
    if sma_20 and sma_20 != 0:
        distance = abs(latest_close - sma_20) / sma_20
    distance_component = clamp(distance * 100, 0, 40)  # cap distance influence

    rsi_component = 0.0
    if rsi_14 is not None:
        if rsi_14 > 70:
            rsi_component = clamp((rsi_14 - 70) * 1.5, 0, 30)
        elif rsi_14 < 30:
            rsi_component = -clamp((30 - rsi_14) * 0.8, 0, 25)

    base = 50 + rsi_component + distance_component
    risk = clamp(base, 0, 100)

    reason_parts = []
    if rsi_14 is not None:
        if rsi_14 > 70:
            reason_parts.append("RSI high")
        elif rsi_14 < 30:
            reason_parts.append("RSI low")
        else:
            reason_parts.append("RSI neutral")
    reason_parts.append("price far from SMA20" if distance_component > 10 else "price near SMA20")
    reason = "; ".join(reason_parts)

    explain = {
        "close": latest_close,
        "sma_20": sma_20,
        "rsi_14": rsi_14,
        "distance_to_SMA": distance,
        "risk_components": {
            "rsi_component": rsi_component,
            "distance_component": distance_component,
        },
        "final_risk_v0": risk,
        "reason": reason,
    }
    return risk, explain


def compute_snapshot(db: Session, symbol: str) -> IndicatorSnapshot:
    """Compute SMA20, RSI14 and risk_v0 for latest price bars and persist snapshot."""
    bars: List[PriceBar] = (
        db.query(PriceBar)
        .filter(PriceBar.symbol == symbol)
        .order_by(PriceBar.ts.desc())
        .limit(200)
        .all()
    )
    if not bars:
        raise HTTPException(status_code=404, detail="No price bars for symbol")

    bars_sorted = list(reversed(bars))  # oldest -> newest
    closes = [b.close for b in bars_sorted if b.close is not None]
    if len(closes) < 20:
        raise HTTPException(status_code=400, detail="Not enough data to compute indicators")

    latest_bar = bars_sorted[-1]
    sma_20_val = sma(closes, 20)
    rsi_14_val = rsi(closes, 14)
    risk_v0_val, explain = compute_risk_v0(latest_bar.close, sma_20_val, rsi_14_val)

    # Upsert snapshot for this symbol/ts
    existing = db.query(IndicatorSnapshot).filter(
        IndicatorSnapshot.symbol == symbol,
        IndicatorSnapshot.ts == latest_bar.ts,
    ).first()
    if existing:
        existing.sma_20 = sma_20_val
        existing.rsi_14 = rsi_14_val
        existing.risk_v0 = risk_v0_val
        existing.explain_json = explain
        db.commit()
        db.refresh(existing)
        return existing

    snapshot = IndicatorSnapshot(
        symbol=symbol,
        ts=latest_bar.ts,
        sma_20=sma_20_val,
        rsi_14=rsi_14_val,
        risk_v0=risk_v0_val,
        explain_json=explain,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot
