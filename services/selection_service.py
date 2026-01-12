"""
Dynamic Top-N Selection Service for Categories

Implements algorithm for selecting most interesting assets from category candidates
with stability (EMA scoring) and data quality awareness.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import and_

from models import Category, Asset, Price, CategoryAsset, SelectionRun
from services import market_data_service

logger = logging.getLogger(__name__)

# Algorithm defaults
DEFAULT_TOP_N = 10
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_EMA_ALPHA = 0.3  # For score smoothing
DEFAULT_REPLACEMENT_DELTA = 0.05  # 5% improvement needed to replace
DEFAULT_MIN_DATA_POINTS = 20  # Minimum price points required


def _calculate_returns(prices: List[float]) -> np.ndarray:
    """Calculate daily returns from price series"""
    if len(prices) < 2:
        return np.array([])
    prices_arr = np.array(prices)
    returns = np.diff(prices_arr) / prices_arr[:-1]
    return returns


def _calculate_volatility(returns: np.ndarray, window: int = 20) -> float:
    """Calculate rolling volatility (annualized)"""
    if len(returns) < window:
        return 0.0
    return float(np.std(returns[-window:]) * np.sqrt(252))


def _calculate_max_drawdown(prices: List[float], window: int = 90) -> float:
    """Calculate maximum drawdown over window"""
    if len(prices) < 2:
        return 0.0
    prices_arr = np.array(prices[-window:])
    cummax = np.maximum.accumulate(prices_arr)
    drawdown = (prices_arr - cummax) / cummax
    return float(np.min(drawdown))


def _calculate_momentum(returns: np.ndarray, window: int = 30) -> float:
    """Calculate momentum (cumulative return over window)"""
    if len(returns) < window:
        return 0.0
    return float(np.prod(1 + returns[-window:]) - 1)


def _calculate_centrality(asset_returns: np.ndarray, category_returns: np.ndarray) -> float:
    """Calculate correlation with category average (proxy for centrality)"""
    if len(asset_returns) < 10 or len(category_returns) < 10:
        return 0.0
    
    # Align lengths
    min_len = min(len(asset_returns), len(category_returns))
    asset_r = asset_returns[-min_len:]
    category_r = category_returns[-min_len:]
    
    if np.std(asset_r) == 0 or np.std(category_r) == 0:
        return 0.0
    
    corr = np.corrcoef(asset_r, category_r)[0, 1]
    return float(abs(corr)) if not np.isnan(corr) else 0.0


def _data_quality_penalty(data_meta: Dict[str, Any]) -> float:
    """
    Calculate penalty based on data quality indicators
    Returns value between 0 (worst) and 1 (best)
    """
    penalty = 1.0
    
    # Stale data
    if data_meta.get("stale"):
        penalty *= 0.7
    
    # Low confidence
    confidence = data_meta.get("confidence")
    if confidence is not None and confidence < 0.5:
        penalty *= 0.8
    
    # Provider issues
    if data_meta.get("provider_disabled") or data_meta.get("rate_limited"):
        penalty *= 0.5
    
    return penalty


def _score_asset(
    asset_id: int,
    prices: List[Tuple[datetime, float, float]],  # (time, close, volume)
    category_returns: np.ndarray,
    weights: Dict[str, float],
    data_meta: Dict[str, Any]
) -> Tuple[float, Dict[str, float]]:
    """
    Calculate composite score for asset
    
    Returns:
        (score, explain_dict)
    """
    if len(prices) < DEFAULT_MIN_DATA_POINTS:
        return 0.0, {"error": "insufficient_data"}
    
    # Extract price and volume series
    close_prices = [p[1] for p in prices]
    volumes = [p[2] if p[2] else 0.0 for p in prices]
    
    returns = _calculate_returns(close_prices)
    if len(returns) == 0:
        return 0.0, {"error": "no_returns"}
    
    # Calculate components
    volatility = _calculate_volatility(returns, window=20)
    max_dd = _calculate_max_drawdown(close_prices, window=90)
    momentum = _calculate_momentum(returns, window=30)
    avg_volume = float(np.mean(volumes)) if volumes else 0.0
    centrality = _calculate_centrality(returns, category_returns)
    quality = _data_quality_penalty(data_meta)
    
    # Normalize components (simple min-max scaling with defaults)
    # Volatility: penalize high volatility (inverse)
    vol_score = max(0, 1 - (volatility / 0.5))  # 50% annual vol = 0 score
    
    # Drawdown: penalize large drawdowns (inverse)
    dd_score = max(0, 1 + max_dd)  # -100% DD = 0 score
    
    # Momentum: reward positive momentum
    mom_score = max(0, min(1, (momentum + 0.3) / 0.6))  # -30% to +30% maps to 0-1
    
    # Liquidity: reward higher volume
    liq_score = min(1, avg_volume / 1_000_000)  # 1M volume = 1.0 score
    
    # Centrality: reward correlation with category
    cent_score = centrality
    
    # Weighted combination
    components = {
        "volatility": vol_score * weights.get("volatility", 0.2),
        "drawdown": dd_score * weights.get("drawdown", 0.25),
        "momentum": mom_score * weights.get("momentum", 0.2),
        "liquidity": liq_score * weights.get("liquidity", 0.15),
        "centrality": cent_score * weights.get("centrality", 0.2),
    }
    
    base_score = sum(components.values())
    final_score = base_score * quality
    
    components["data_quality"] = quality
    components["total"] = final_score
    
    return final_score, components


def _get_category_average_returns(
    db: Session,
    category_id: int,
    lookback_days: int
) -> np.ndarray:
    """Calculate average returns for all candidates in category"""
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    
    # Get all candidate assets
    candidates = (
        db.query(CategoryAsset)
        .filter(
            and_(
                CategoryAsset.category_id == category_id,
                CategoryAsset.is_candidate == True
            )
        )
        .all()
    )
    
    if not candidates:
        return np.array([])
    
    all_returns = []
    for ca in candidates:
        prices = (
            db.query(Price.time, Price.close)
            .filter(
                and_(
                    Price.asset_id == ca.asset_id,
                    Price.time >= cutoff
                )
            )
            .order_by(Price.time)
            .all()
        )
        
        if len(prices) >= DEFAULT_MIN_DATA_POINTS:
            close_list = [p[1] for p in prices]
            returns = _calculate_returns(close_list)
            if len(returns) > 0:
                all_returns.append(returns)
    
    if not all_returns:
        return np.array([])
    
    # Align lengths and average
    min_len = min(len(r) for r in all_returns)
    aligned = np.array([r[-min_len:] for r in all_returns])
    return np.mean(aligned, axis=0)


def preview_category_selection(
    db: Session,
    category_id: int,
    top_n: int = DEFAULT_TOP_N,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    weights: Dict[str, float] | None = None
) -> Dict[str, Any]:
    """
    Preview selection without persisting
    
    Returns:
        {
            "selected": [...],
            "candidates": [...],
            "meta": {"category_id", "top_n", "lookback_days", "weights"}
        }
    """
    if weights is None:
        weights = {
            "volatility": 0.2,
            "drawdown": 0.25,
            "momentum": 0.2,
            "liquidity": 0.15,
            "centrality": 0.2,
        }
    
    # Verify category exists
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        return {
            "error": "category_not_found",
            "selected": [],
            "candidates": [],
            "meta": {}
        }
    
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    
    # Get candidates
    candidates = (
        db.query(CategoryAsset, Asset)
        .join(Asset, CategoryAsset.asset_id == Asset.id)
        .filter(
            and_(
                CategoryAsset.category_id == category_id,
                CategoryAsset.is_candidate == True
            )
        )
        .all()
    )
    
    if not candidates:
        return {
            "selected": [],
            "candidates": [],
            "meta": {
                "category_id": category_id,
                "top_n": top_n,
                "lookback_days": lookback_days,
                "weights": weights,
                "note": "no_candidates"
            }
        }
    
    # Calculate category average returns
    category_returns = _get_category_average_returns(db, category_id, lookback_days)
    
    # Score each candidate
    scored_candidates = []
    for ca, asset in candidates:
        # Fetch price data
        prices = (
            db.query(Price.time, Price.close, Price.volume)
            .filter(
                and_(
                    Price.asset_id == asset.id,
                    Price.time >= cutoff
                )
            )
            .order_by(Price.time)
            .all()
        )
        
        # Get data quality metadata from market_data_service if available
        data_meta = {}
        try:
            # Try to get fresh snapshot to check data quality
            snapshot = market_data_service.get_snapshot(asset.symbol)
            data_meta = {
                "source": snapshot.get("source"),
                "cached": snapshot.get("cached"),
                "stale": snapshot.get("stale"),
                "confidence": snapshot.get("confidence"),
            }
        except Exception:
            # Fallback to no metadata
            pass
        
        score, explain = _score_asset(
            asset.id,
            prices,
            category_returns,
            weights,
            data_meta
        )
        
        scored_candidates.append({
            "asset_id": asset.id,
            "symbol": asset.symbol,
            "name": asset.name,
            "score": score,
            "explain": explain,
            "data_meta": data_meta,
            "current_ema": ca.score_ema,
        })
    
    # Sort by score descending
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    
    # Select top N
    selected = scored_candidates[:top_n]
    
    # Add ranks
    for idx, item in enumerate(selected):
        item["rank"] = idx + 1
    
    return {
        "selected": selected,
        "candidates": scored_candidates,
        "meta": {
            "category_id": category_id,
            "category_name": category.name,
            "top_n": top_n,
            "lookback_days": lookback_days,
            "weights": weights,
            "total_candidates": len(scored_candidates),
        }
    }


def recompute_category_selection(
    db: Session,
    category_id: int,
    top_n: int = DEFAULT_TOP_N,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    weights: Dict[str, float] | None = None,
    persist: bool = True
) -> Dict[str, Any]:
    """
    Recompute selection with persistence and EMA smoothing
    
    Updates CategoryAsset flags (is_selected, last_score, score_ema, last_rank)
    Creates SelectionRun record
    
    Returns same format as preview_category_selection
    """
    result = preview_category_selection(db, category_id, top_n, lookback_days, weights)
    
    if not persist or "error" in result:
        return result
    
    # Update CategoryAsset records with EMA smoothing
    for candidate in result["candidates"]:
        ca = (
            db.query(CategoryAsset)
            .filter(
                and_(
                    CategoryAsset.category_id == category_id,
                    CategoryAsset.asset_id == candidate["asset_id"]
                )
            )
            .first()
        )
        
        if ca:
            # Update score with EMA
            new_score = candidate["score"]
            if ca.score_ema is not None:
                ca.score_ema = DEFAULT_EMA_ALPHA * new_score + (1 - DEFAULT_EMA_ALPHA) * ca.score_ema
            else:
                ca.score_ema = new_score
            
            ca.last_score = new_score
            
            # Determine selection based on rank
            is_in_top_n = candidate in result["selected"]
            
            # Stability hysteresis: only change selection if:
            # - New asset significantly better than last selected, OR
            # - Current selected asset no longer in top positions
            if is_in_top_n:
                ca.is_selected = True
                ca.last_rank = candidate.get("rank")
                ca.last_selected_at = datetime.utcnow()
            else:
                # Check if should deselect
                if ca.is_selected:
                    # Simple rule: deselect if not in top N*1.2 (buffer zone)
                    buffer_rank = int(top_n * 1.2)
                    current_rank = result["candidates"].index(candidate) + 1
                    if current_rank > buffer_rank:
                        ca.is_selected = False
                        ca.last_rank = current_rank
                else:
                    ca.last_rank = result["candidates"].index(candidate) + 1
    
    # Create SelectionRun record
    run = SelectionRun(
        category_id=category_id,
        top_n=top_n,
        lookback_days=lookback_days,
        weights_json=weights or {},
        results_json={
            "selected": [
                {
                    "asset_id": s["asset_id"],
                    "symbol": s["symbol"],
                    "score": s["score"],
                    "rank": s.get("rank"),
                    "explain": s["explain"]
                }
                for s in result["selected"]
            ],
            "meta": result["meta"]
        }
    )
    
    db.add(run)
    db.commit()
    
    logger.info(f"Selection recomputed for category {category_id}: {len(result['selected'])} selected")
    
    return result


def get_current_selection(
    db: Session,
    category_id: int,
    top_n: int = DEFAULT_TOP_N
) -> Dict[str, Any]:
    """
    Get currently selected assets based on persisted flags
    
    Returns same format as preview but from database state
    """
    selected_records = (
        db.query(CategoryAsset, Asset)
        .join(Asset, CategoryAsset.asset_id == Asset.id)
        .filter(
            and_(
                CategoryAsset.category_id == category_id,
                CategoryAsset.is_selected == True
            )
        )
        .order_by(CategoryAsset.last_rank.asc())
        .limit(top_n)
        .all()
    )
    
    selected = []
    for ca, asset in selected_records:
        selected.append({
            "asset_id": asset.id,
            "symbol": asset.symbol,
            "name": asset.name,
            "score": ca.last_score,
            "rank": ca.last_rank,
            "score_ema": ca.score_ema,
            "last_selected_at": ca.last_selected_at.isoformat() if ca.last_selected_at else None,
        })
    
    category = db.query(Category).filter(Category.id == category_id).first()
    
    return {
        "selected": selected,
        "meta": {
            "category_id": category_id,
            "category_name": category.name if category else None,
            "source": "persisted_flags",
        }
    }
