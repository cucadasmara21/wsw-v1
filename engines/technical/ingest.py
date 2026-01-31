"""
Technical ingestion engine: fetch OHLCV, compute metrics, store meta32
P-03: work_cap enforced in batch loop.
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import concurrent.futures
import time

from models import Asset, Price, AssetMetricSnapshot
from engines.technical.providers.yfinance_provider import fetch_ohlcv as yf_fetch, is_crypto_symbol
from engines.technical.providers.coingecko_provider import fetch_ohlcv as cg_fetch
from engines.technical.metrics import compute_metrics_from_bars

logger = logging.getLogger(__name__)


def ingest_asset(
    db: Session,
    asset: Asset,
    interval: str = "1d",
    limit: int = 90
) -> Dict[str, any]:
    """
    Ingest data for a single asset.
    
    Returns:
        Dict with: ok, error, bars_count, metrics_computed
    """
    try:
        symbol = asset.symbol
        
        if is_crypto_symbol(symbol):
            bars = cg_fetch(symbol, interval, limit)
        else:
            bars = yf_fetch(symbol, interval, limit)
        
        if not bars:
            return {'ok': False, 'error': 'No data', 'bars_count': 0, 'metrics_computed': False}
        
        bars_inserted = 0
        for bar in bars:
            try:
                price = Price(
                    time=bar['ts'],
                    asset_id=asset.id,
                    open=bar.get('open'),
                    high=bar.get('high'),
                    low=bar.get('low'),
                    close=bar['close'],
                    volume=bar.get('volume')
                )
                db.merge(price)
                bars_inserted += 1
            except Exception as e:
                logger.debug(f"Price insert failed for {symbol} @ {bar['ts']}: {e}")
        
        db.commit()
        
        metrics = compute_metrics_from_bars(bars, asset.id)
        if metrics:
            snapshot = AssetMetricSnapshot(
                asset_id=asset.id,
                as_of=datetime.utcnow(),
                metrics={
                    'risk01': metrics['risk01'],
                    'shock01': metrics['shock01'],
                    'trend': metrics['trend'],
                    'volatility01': metrics['volatility01'],
                    'meta32': metrics['meta32']
                },
                quality={'bars_count': len(bars)},
                explain={}
            )
            db.merge(snapshot)
            db.commit()
            
            x, y = generate_coordinates(asset.id, asset.category_id or 0)
            
            db.execute(text("""
                UPDATE assets 
                SET meta32 = :meta32,
                    x = :x,
                    y = :y
                WHERE id = :asset_id
            """), {
                "meta32": metrics['meta32'],
                "x": x,
                "y": y,
                "asset_id": asset.id
            })
            db.commit()
        
        return {
            'ok': True,
            'error': None,
            'bars_count': bars_inserted,
            'metrics_computed': metrics is not None
        }
    except Exception as e:
        logger.error(f"Ingest failed for {asset.symbol}: {e}")
        db.rollback()
        return {'ok': False, 'error': str(e), 'bars_count': 0, 'metrics_computed': False}


def ingest_batch(
    db: Session,
    assets: List[Asset],
    interval: str = "1d",
    limit: int = 90,
    concurrency: int = 4
) -> Dict:
    """
    Ingest batch of assets with concurrency control.
    P-03: processes at most WORK_CAP_PER_TICK per batch; chunks deterministically.
    
    Returns:
        Dict with: ok_count, fail_count, total_bars, duration_ms
    """
    from engines.constants import WORK_CAP_PER_TICK

    start_time = time.time()
    ok_count = 0
    fail_count = 0
    total_bars = 0

    # P-03: chunk by work_cap (bounded per batch)
    for chunk_start in range(0, len(assets), WORK_CAP_PER_TICK):
        chunk = assets[chunk_start : chunk_start + WORK_CAP_PER_TICK]
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(ingest_asset, db, asset, interval, limit): asset for asset in chunk}
        
            for future in concurrent.futures.as_completed(futures):
                asset = futures[future]
                try:
                    result = future.result()
                    if result['ok']:
                        ok_count += 1
                        total_bars += result['bars_count']
                    else:
                        fail_count += 1
                except Exception as e:
                    logger.error(f"Future failed for {asset.symbol}: {e}")
                    fail_count += 1

    duration_ms = int((time.time() - start_time) * 1000)
    
    return {
        'ok_count': ok_count,
        'fail_count': fail_count,
        'total_bars': total_bars,
        'duration_ms': duration_ms
    }
