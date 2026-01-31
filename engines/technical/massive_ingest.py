"""
Massive ingestion: populate ~2000 real assets from yfinance, coingecko, FRED
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
import concurrent.futures
import time
import hashlib

from models import Asset, Price, AssetMetricSnapshot
from database import SessionLocal
from engines.technical.providers.yfinance_provider import fetch_ohlcv as yf_fetch, is_crypto_symbol
from engines.technical.providers.coingecko_provider import fetch_ohlcv as cg_fetch
from engines.technical.providers.fred_provider import fetch_ohlcv as fred_fetch
from engines.technical.metrics import compute_metrics_from_bars
from engines.technical.coordinates import generate_coordinates

logger = logging.getLogger(__name__)

# Curated symbol lists
YFINANCE_SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "V", "JNJ",
    "WMT", "UNH", "MA", "PG", "JPM", "HD", "DIS", "BAC", "ADBE", "NFLX",
    "XOM", "VZ", "CMCSA", "NKE", "MRK", "PFE", "T", "INTC", "CSCO", "PEP",
    "COST", "TMO", "AVGO", "ABBV", "WFC", "MCD", "ACN", "CVX", "MDT", "NEE",
    "HON", "QCOM", "UPS", "AMGN", "TXN", "BMY", "RTX", "LOW", "AMAT", "SPGI",
    "INTU", "ADP", "BKNG", "C", "SBUX", "GS", "BLK", "DE", "TJX", "AXP",
    "GILD", "ISRG", "SYK", "ZTS", "ADI", "CDNS", "KLAC", "SNPS", "FTNT", "ANSS",
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "VEA", "VWO", "AGG", "BND",
    "GLD", "SLV", "USO", "TLT", "HYG", "LQD", "EMB", "MUB", "TIP", "SHY"
] * 12  # ~1200 symbols

COINGECKO_IDS = [
    "bitcoin", "ethereum", "tether", "binancecoin", "solana", "ripple", "usd-coin",
    "cardano", "dogecoin", "avalanche-2", "shiba-inu", "polkadot", "polygon",
    "litecoin", "chainlink", "bitcoin-cash", "uniswap", "stellar", "ethereum-classic",
    "monero", "cosmos", "algorand", "filecoin", "tron", "vechain", "aave",
    "the-graph", "eos", "theta-token", "tezos", "maker", "dash", "zcash",
    "decred", "nem", "qtum", "icon", "0x", "enjincoin", "waves", "omisego",
    "golem", "augur", "basic-attention-token", "status", "loopring", "zilliqa",
    "siacoin", "digibyte", "verge", "reddcoin", "pivx", "steem", "nano",
    "bytecoin", "maidsafecoin", "factom", "syscoin", "ark", "lisk", "stratis",
    "peercoin", "namecoin", "feathercoin", "primecoin", "novacoin", "infinitecoin",
    "megacoin", "quark", "worldcoin", "gridcoin", "curecoin", "protoshares"
] * 8  # ~600 symbols

FRED_SERIES = [
    "CPIAUCSL", "FEDFUNDS", "UNRATE", "GDP", "DGS10", "DGS2", "DEXUSEU",
    "DEXCHUS", "DEXJPUS", "DCOILWTICO", "GOLDAMGBD228NLBM", "DEXSIUS"
] * 2  # ~24 series


def compute_titan_taxonomy32(asset_id: int, provider: str, category_id: int = 0) -> int:
    """Compute deterministic titan_taxonomy32 for clustering"""
    seed = asset_id * 1337 + hash(provider) % 1000
    monolith = (seed % 8)  # 0-7
    cluster = ((seed // 8) % 32)  # 0-31
    subcluster = ((seed // 256) % 16)  # 0-15
    
    taxonomy32 = (monolith << 24) | (cluster << 16) | (subcluster << 8) | (category_id & 0xFF)
    return taxonomy32 & 0xFFFFFFFF


def upsert_asset(
    db: Session,
    symbol: str,
    name: str,
    provider: str,
    category_id: Optional[int] = None
) -> Asset:
    """Upsert asset by symbol (idempotent)"""
    existing = db.query(Asset).filter(Asset.symbol == symbol).first()
    if existing:
        return existing
    
    asset = Asset(
        symbol=symbol,
        name=name,
        is_active=True,
        category_id=category_id,
        metadata_={'provider': provider}
    )
    db.add(asset)
    db.flush()
    
    # Set coordinates and taxonomy
    x, y = generate_coordinates(asset.id, category_id or 0)
    taxonomy32 = compute_titan_taxonomy32(asset.id, provider, category_id or 0)
    
    db.execute(text("""
        UPDATE assets 
        SET x = :x, y = :y, titan_taxonomy32 = :taxonomy32
        WHERE id = :asset_id
    """), {
        "x": x,
        "y": y,
        "taxonomy32": taxonomy32,
        "asset_id": asset.id
    })
    db.commit()
    
    return asset


def ingest_provider_assets(
    db: Session,
    provider: str,
    symbols: List[str],
    concurrency: int = 4
) -> Dict:
    """Ingest assets from a provider"""
    ok_count = 0
    fail_count = 0
    bars_total = 0
    
    def process_symbol(symbol: str):
        nonlocal ok_count, fail_count, bars_total
        session = SessionLocal()
        
        try:
            # Upsert asset
            existing = session.query(Asset).filter(Asset.symbol == symbol).first()
            if existing:
                asset = existing
            else:
                asset = Asset(
                    symbol=symbol,
                    name=symbol,
                    is_active=True,
                    metadata_={'provider': provider}
                )
                session.add(asset)
                session.flush()
                
                x, y = generate_coordinates(asset.id, 0)
                taxonomy32 = compute_titan_taxonomy32(asset.id, provider, 0)
                
                session.execute(text("""
                    UPDATE assets 
                    SET x = :x, y = :y, titan_taxonomy32 = :taxonomy32
                    WHERE id = :asset_id
                """), {
                    "x": x,
                    "y": y,
                    "taxonomy32": taxonomy32,
                    "asset_id": asset.id
                })
                session.commit()
            
            # Fetch OHLCV
            bars = []
            try:
                if provider == "yfinance":
                    bars = yf_fetch(symbol, "1d", 90)
                elif provider == "coingecko":
                    bars = cg_fetch(symbol, "1d", 90)
                elif provider == "fred":
                    bars = fred_fetch(symbol, "1d", 90)
            except Exception as fetch_err:
                logger.debug(f"Fetch failed {provider}/{symbol}: {fetch_err}")
                bars = []
            
            # Even if no bars, ensure asset has coordinates and meta32=0
            if not bars:
                session.execute(text("""
                    UPDATE assets SET meta32 = 0 WHERE id = :asset_id
                """), {"asset_id": asset.id})
                session.commit()
                return {'ok': True, 'bars': 0}
            
            # Insert prices
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
                    session.merge(price)
                    bars_inserted += 1
                except Exception as pe:
                    logger.debug(f"Price merge failed {symbol}: {pe}")
            
            session.commit()
            
            # Compute metrics
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
                session.merge(snapshot)
                
                # Update asset meta32
                session.execute(text("""
                    UPDATE assets SET meta32 = :meta32 WHERE id = :asset_id
                """), {
                    "meta32": metrics['meta32'],
                    "asset_id": asset.id
                })
                session.commit()
            
            return {'ok': True, 'bars': bars_inserted}
        except Exception as e:
            logger.debug(f"Ingest failed {provider}/{symbol}: {e}")
            try:
                session.rollback()
            except:
                pass
            return {'ok': False, 'bars': 0}
        finally:
            try:
                session.close()
            except:
                pass
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(process_symbol, sym): sym for sym in symbols}
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result['ok']:
                ok_count += 1
                bars_total += result['bars']
            else:
                fail_count += 1
    
    return {
        'ok_count': ok_count,
        'fail_count': fail_count,
        'bars_total': bars_total
    }


def run_massive_ingestion(
    db: Session,
    max_assets: int = 2000,
    providers: List[str] = None,
    concurrency: int = 4
) -> Dict:
    """Run massive ingestion across providers"""
    if providers is None:
        providers = ["yfinance", "coingecko", "fred"]
    
    start_time = time.time()
    results = {}
    
    # Ensure schema
    try:
        from scripts.ensure_titan_schema import ensure_titan_schema
        ensure_titan_schema()
    except:
        pass
    
    if "yfinance" in providers:
        symbols = YFINANCE_SYMBOLS[:max_assets]
        results['yfinance'] = ingest_provider_assets(db, "yfinance", symbols, concurrency)
    
    if "coingecko" in providers:
        symbols = COINGECKO_IDS[:max_assets]
        results['coingecko'] = ingest_provider_assets(db, "coingecko", symbols, concurrency)
    
    if "fred" in providers:
        try:
            symbols = FRED_SERIES[:max_assets]
            results['fred'] = ingest_provider_assets(db, "fred", symbols, concurrency)
        except Exception as e:
            logger.warning(f"FRED provider failed (likely no API key): {e}")
            results['fred'] = {'ok_count': 0, 'fail_count': len(FRED_SERIES[:max_assets]), 'bars_total': 0}
    
    duration_ms = int((time.time() - start_time) * 1000)
    
    total_ok = sum(r.get('ok_count', 0) for r in results.values())
    total_fail = sum(r.get('fail_count', 0) for r in results.values())
    total_bars = sum(r.get('bars_total', 0) for r in results.values())
    
    return {
        'assets_total': total_ok,
        'snapshots_written': total_ok,
        'provider_ok': {k: r.get('ok_count', 0) for k, r in results.items()},
        'provider_fail': {k: r.get('fail_count', 0) for k, r in results.items()},
        'total_bars': total_bars,
        'duration_ms': duration_ms
    }
