from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Dict
from typing import List
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Engine

from config import settings
from database import engine as default_engine
from scripts.ensure_titan_schema import ensure_schema
from datetime import datetime

logger = logging.getLogger(__name__)


def _hash_symbol(symbol: str) -> int:
    h = hash(symbol) & 0xFFFFFFFF
    return h


def _u01_from_hash(h: int) -> float:
    return float(h & 0xFFFFFF) / float(0x1000000)


def _pack_meta32(shock8: int, risk8: int, trend2: int, vital6: int, macro8: int) -> int:
    shock8 &= 0xFF
    risk8 &= 0xFF
    trend2 &= 0x03
    vital6 &= 0x3F
    macro8 &= 0xFF
    return shock8 | (risk8 << 8) | (trend2 << 16) | (vital6 << 18) | (macro8 << 24)


def _pack_taxonomy32(domain_id: int, cluster_id: int, category_id: int, sub_id: int) -> int:
    domain_id = max(1, min(6, domain_id))
    cluster_id &= 0xFF
    category_id &= 0xFF
    sub_id &= 0xF
    return (domain_id << 24) | (cluster_id << 16) | (category_id << 8) | sub_id


_fred_cache: dict[str, tuple[float, float]] = {}

async def fetch_fred_macro() -> float:
    if not settings.FRED_API_KEY:
        return 0.5

    import time
    cache_key = 'macro'
    now = time.time()
    
    if cache_key in _fred_cache:
        cached_val, cached_time = _fred_cache[cache_key]
        if now - cached_time < 60.0:
            return cached_val

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            fed_url = f"https://api.stlouisfed.org/fred/series/observations?series_id=FEDFUNDS&api_key={settings.FRED_API_KEY}&file_type=json&limit=1&sort_order=desc"
            cpi_url = f"https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key={settings.FRED_API_KEY}&file_type=json&limit=1&sort_order=desc"
            
            fed_resp = await client.get(fed_url)
            cpi_resp = await client.get(cpi_url)
            
            if fed_resp.status_code == 200 and cpi_resp.status_code == 200:
                fed_data = fed_resp.json()
                cpi_data = cpi_resp.json()
                
                fed_obs = fed_data.get('observations', [])
                cpi_obs = cpi_data.get('observations', [])
                
                if fed_obs and cpi_obs:
                    fed_val = float(fed_obs[0].get('value', 0))
                    cpi_val = float(cpi_obs[0].get('value', 0))
                    
                    if fed_val and cpi_val:
                        macro_scalar = (fed_val / 10.0 + cpi_val / 300.0) / 2.0
                        macro_scalar = max(0.0, min(1.0, macro_scalar))
                        _fred_cache[cache_key] = (macro_scalar, now)
                        return macro_scalar
    except Exception as e:
        logger.warning(f"FRED fetch failed: {e}")
    
    return 0.5


def _get_static_symbols() -> List[str]:
    equity = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "JPM", "V", "PG", "UNH",
        "HD", "MA", "PYPL", "ADBE", "CMCSA", "NFLX", "INTC", "CSCO", "PEP", "KO",
    ] * 10
    crypto = [
        "BTC", "ETH", "BNB", "SOL", "ADA", "XRP", "DOT", "DOGE", "AVAX", "MATIC",
    ] * 20
    macro = ["FEDFUNDS", "CPIAUCSL", "UNRATE", "GDP", "MORTGAGE30US"] * 4
    return (equity + crypto + macro)[:2000]


KAPPA_MIN = 1e-3  # P-02: denominator clamp (BOHRIUM)


def normalize_signal(x: float, k: float = 1.0) -> float:
    """
    Normalize signal using tanh: norm(x) = 0.5 + 0.5*tanh(x/k)
    Maps unbounded input to [0..1] range with smooth saturation.
    P-02: k = max(k, KAPPA_MIN) before division.
    """
    k_safe = max(k, KAPPA_MIN)
    return 0.5 + 0.5 * math.tanh(x / k_safe)


async def _compute_asset_metrics(symbol: str, domain_id: int, macro_scalar: float) -> Dict:
    """
    Compute asset metrics with real motor signals (normalized).
    TODO: Replace hash-based signals with actual CUSUM, volatility, RLS slope when bars available.
    """
    h = _hash_symbol(symbol)
    h1 = _hash_symbol(symbol + "vol")
    h2 = _hash_symbol(symbol + "liq")

    vol_norm = _u01_from_hash(h1)
    drawdown = _u01_from_hash(h2) * 0.3
    liq = _u01_from_hash(h ^ 0x1234)
    momentum = (_u01_from_hash(h ^ 0x5678) - 0.5) * 0.4

    # Position computation (unchanged)
    cri = vol_norm * 0.55 + drawdown * 0.25 + (1.0 - liq) * 0.20
    radius = 0.15 + 0.70 * cri
    radius = max(0.0, min(1.0, radius))
    angle_hash = _hash_symbol(symbol + "angle")
    angle = 2.0 * math.pi * _u01_from_hash(angle_hash)
    x = 0.5 + radius * math.cos(angle) * 0.5
    y = 0.5 + radius * math.sin(angle) * 0.5
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))

    # Motor signals with normalization
    # Shock: CUSUM magnitude or jump z-score (normalized)
    shock_raw = abs(momentum) + vol_norm * 0.5
    shock = normalize_signal(shock_raw * 4.0 - 2.0, k=2.0)  # Map [0..1.5] -> normalized
    
    # Risk: composite (vol + liquidity + drift) (normalized)
    risk_raw = vol_norm * 0.4 + (1.0 - liq) * 0.3 + abs(drawdown) * 0.3
    risk = normalize_signal(risk_raw * 3.0 - 1.5, k=1.5)  # Map [0..1] -> normalized
    
    # Trend: RLS slope / regime (0=flat, 1=bull, 2=bear)
    trend2 = 0 if abs(momentum) < 0.05 else (1 if momentum > 0 else 2)
    
    # Vital: data completeness / liquidity (normalized)
    vital_raw = (0.55 * (1.0 - cri)) + (0.25 * liq) + (0.20 * (1.0 - drawdown))
    vital = normalize_signal(vital_raw * 2.0 - 1.0, k=1.0)  # Map [0..1] -> normalized
    
    # Macro: normalized macro pressure (from FRED cache)
    macro = normalize_signal(macro_scalar * 2.0 - 1.0, k=1.0)  # Map [0..1] -> normalized

    # Pack into meta32 exactly: shock8 | risk8<<8 | trend2<<16 | vital6<<18 | macro8<<24
    shock8 = int(round(shock * 255.0)) & 0xFF
    risk8 = int(round(risk * 255.0)) & 0xFF
    trend2 = int(trend2) & 0x03
    vital6 = int(round(vital * 63.0)) & 0x3F
    macro8 = int(round(macro * 255.0)) & 0xFF

    # Handle edge case: very low vitality (zombie assets)
    if (_hash_symbol(symbol + "zombie") % 100) < 5:
        vital6 = (_hash_symbol(symbol + "zombie2") % 4)

    meta32 = _pack_meta32(shock8, risk8, trend2, vital6, macro8)

    cluster_id = (_hash_symbol(symbol + "cluster") % 100) & 0xFF
    category_id = (_hash_symbol(symbol + "cat") % 50) & 0xFF
    sub_id = (_hash_symbol(symbol + "sub") % 10) & 0xF
    taxonomy32 = _pack_taxonomy32(domain_id, cluster_id, category_id, sub_id)

    return {
        "symbol": symbol,
        "name": f"Asset {symbol}",
        "x": x,
        "y": y,
        "meta32": meta32,
        "titan_taxonomy32": taxonomy32,
    }


# P-03: Deterministic real-time budget (work_cap per tick)
from engines.constants import WORK_CAP_PER_TICK


async def ingest_run(limit_assets: int, concurrency: int) -> Dict:
    ensure_schema(default_engine)

    macro_scalar = await fetch_fred_macro()

    symbols = _get_static_symbols()[:limit_assets]

    domain_ids = [1, 2, 3, 4, 5, 6]
    semaphore = asyncio.Semaphore(concurrency)

    async def process_symbol(symbol: str, idx: int):
        async with semaphore:
            domain_id = domain_ids[idx % len(domain_ids)]
            return await _compute_asset_metrics(symbol, domain_id, macro_scalar)

    # P-03: Process in chunks of WORK_CAP_PER_TICK (bounded work per batch)
    all_results = []
    for chunk_start in range(0, len(symbols), WORK_CAP_PER_TICK):
        chunk = symbols[chunk_start : chunk_start + WORK_CAP_PER_TICK]
        tasks = [process_symbol(sym, chunk_start + i) for i, sym in enumerate(chunk)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_results.extend(results)
    results = all_results

    assets_data = []
    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"Asset processing failed: {result}")
            continue
        if result:
            assets_data.append(result)

    if not assets_data:
        return {"inserted": 0, "updated": 0, "provider_modes": {}, "macro_mode": "fallback"}

    inserted = 0
    updated = 0
    ts_now = datetime.utcnow().isoformat()

    try:
        with default_engine.begin() as conn:
            for asset in assets_data:
                try:
                    result = conn.execute(
                        text(
                            """
                            INSERT INTO assets (symbol, name, x, y, titan_taxonomy32, meta32)
                            VALUES (:symbol, :name, :x, :y, :titan_taxonomy32, :meta32)
                            ON CONFLICT(symbol) DO UPDATE SET
                                x = EXCLUDED.x,
                                y = EXCLUDED.y,
                                titan_taxonomy32 = EXCLUDED.titan_taxonomy32,
                                meta32 = EXCLUDED.meta32
                            """
                        ),
                        asset,
                    )
                    
                    existing_row = conn.execute(
                        text("SELECT id FROM assets WHERE symbol = :symbol"),
                        {"symbol": asset["symbol"]}
                    ).fetchone()
                    
                    asset_id = existing_row.id if existing_row else result.lastrowid
                    
                    if asset_id:
                        shock8 = asset["meta32"] & 0xFF
                        risk8 = (asset["meta32"] >> 8) & 0xFF
                        trend2 = (asset["meta32"] >> 16) & 0x03
                        vital6 = (asset["meta32"] >> 18) & 0x3F
                        macro8 = (asset["meta32"] >> 24) & 0xFF
                        
                        conn.execute(
                            text(
                                """
                                INSERT INTO metrics_snapshot (asset_id, ts, meta32, risk, shock, trend, vitality, macro)
                                VALUES (:asset_id, :ts, :meta32, :risk, :shock, :trend, :vitality, :macro)
                                """
                            ),
                            {
                                "asset_id": asset_id,
                                "ts": ts_now,
                                "meta32": asset["meta32"],
                                "risk": float(risk8) / 255.0,
                                "shock": float(shock8) / 255.0,
                                "trend": int(trend2),
                                "vitality": int(vital6),
                                "macro": int(macro8),
                            }
                        )
                    
                    if existing_row:
                        updated += 1
                    else:
                        inserted += 1
                except Exception as e:
                    logger.warning(f"Failed to upsert {asset['symbol']}: {e}")
    except Exception as e:
        logger.error(f"Batch insert failed: {e}")

    provider_modes = {
        "polygon": "skipped" if not settings.POLYGON_API_KEY else "available",
        "eodhd": "skipped" if not settings.EODHD_API_KEY else "available",
        "fred": "active" if settings.FRED_API_KEY else "fallback",
    }

    return {
        "inserted": inserted,
        "updated": updated,
        "provider_modes": provider_modes,
        "macro_mode": "fred" if settings.FRED_API_KEY else "fallback",
    }
