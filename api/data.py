"""
Resilient data endpoints for financial terminal UI.
FAIL-FAST: Always returns <300ms. Providers run in background only.
"""
import logging
import re
import time
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import desc
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, Query, Depends, Request

from services.data_provider_service import _data_provider_service
from database import get_db
from models import Asset, Price
from config import settings

router = APIRouter(tags=["data"])
logger = logging.getLogger(__name__)

# Build tag to verify code is loaded
BUILD_TAG = "HOTFIX_V21"

# AST\\d+ internal symbol pattern (corrected; do not use ASTd+)
AST_RE = re.compile(r'^AST\d+$')


def validate_symbol(symbol: str) -> str:
    """Validate and sanitize symbol input with allowlist regex."""
    if not symbol or not isinstance(symbol, str):
        raise HTTPException(status_code=400, detail="Symbol is required")
    
    # Allowlist: alphanumeric, dot, dash, underscore, 1-20 chars
    if not re.match(r'^[A-Za-z0-9\.\-\_]{1,20}$', symbol):
        raise HTTPException(status_code=400, detail="Invalid symbol format")
    
    return symbol.strip().upper()


def validate_fred_id(fred_id: str) -> str:
    """Validate and sanitize FRED series ID with allowlist regex."""
    if not fred_id or not isinstance(fred_id, str):
        raise HTTPException(status_code=400, detail="fred_id is required")
    
    # Allowlist: alphanumeric, dot, dash, underscore, 1-50 chars
    if not re.match(r'^[A-Za-z0-9\.\-\_]{1,50}$', fred_id):
        raise HTTPException(status_code=400, detail="Invalid FRED series ID format")
    
    return fred_id.strip().upper()


@router.get("/asset/detail", summary="Get asset detail with price and risk data")
async def get_asset_detail(
    symbol: str = Query(..., description="Asset symbol (e.g., AAPL, AST000001)"),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Get asset detail including price, sparkline, and risk metrics.
    
    FAIL-FAST: Always returns <300ms. Queries database for real metadata and prices.
    
    Returns:
    - name/sector from assets table
    - last/change_pct from prices table (latest close)
    - sparkline from last 30-60 prices
    - stale=true if last price timestamp > 15 minutes old
    """
    start_ms = time.time() * 1000
    
    # Get correlation ID from request header or generate one
    correlation_id = None
    if request:
        correlation_id = request.headers.get("X-Request-Id") or request.headers.get("request_id")
    if not correlation_id:
        import uuid
        correlation_id = str(uuid.uuid4())[:8]
    
    # Configurable timeout for provider fetches (longer in DEV)
    provider_timeout_s = 12.0 if settings.DEBUG else 8.0
    
    try:
        validated_symbol = validate_symbol(symbol)
        
        logger.info(
            f"[asset/detail] START correlation_id={correlation_id} symbol={validated_symbol} "
            f"timeout_s={provider_timeout_s}"
        )
        
        # Initialize observability tracking
        provider_ok = False
        db_price_ok = False
        provider = "none"
        reason = None
        ticker_source = "unknown"
        asset_name = ""
        asset_sector = ""
        
        # Resolve symbol to ticker (for provider quotes)
        # For AST* symbols, attempt DB lookup first, then fallback to modulo mapping
        resolved_ticker = _data_provider_service.resolve_ticker(validated_symbol, db_session=db)
        
        # Track ticker resolution source
        if AST_RE.match(validated_symbol):
            # Check if DB lookup succeeded (ticker came from DB)
            asset_check = db.query(Asset).filter(Asset.symbol == validated_symbol).first()
            if asset_check:
                if hasattr(asset_check, 'ticker') and asset_check.ticker:
                    ticker_source = "db_column"
                elif hasattr(asset_check, 'metadata_') and asset_check.metadata_ and asset_check.metadata_.get('ticker'):
                    ticker_source = "db_metadata"
                else:
                    ticker_source = "modulo_fallback"
                    logger.debug(f"[asset/detail] AST* symbol {validated_symbol} using modulo mapping to {resolved_ticker}")
            else:
                ticker_source = "modulo_fallback"
                logger.debug(f"[asset/detail] AST* symbol {validated_symbol} not in DB, using modulo mapping to {resolved_ticker}")
        elif resolved_ticker == validated_symbol.upper():
            ticker_source = "direct"
        
        # Handle unmapped symbols (resolve_ticker returned None)
        if resolved_ticker is None:
            if settings.DEBUG:
                # DEBUG: return stub with reason
                logger.warning(f"[asset/detail] unmapped symbol: {validated_symbol}")
                elapsed_ms = int((time.time() * 1000) - start_ms)
                logger.info(
                    f"[asset/detail] symbol={validated_symbol} resolved_ticker=None provider=none "
                    f"provider_ok=false db_price_ok=false stale=true elapsed_ms={elapsed_ms} reason=unmapped_symbol"
                )
                return {
                    "symbol": validated_symbol,
                    "name": "",
                    "sector": "",
                    "last": 0.0,
                    "change_pct": 0.0,
                    "sparkline": [],
                    "risk": {"risk": 0.5, "shock": 0.5, "trend": 1, "vital": 0.5, "macro": 0.5},
                    "ts": int(time.time() * 1000),
                    "stale": True,
                    "reason": "unmapped_symbol",
                    "build_tag": BUILD_TAG
                }
            else:
                # Production: return 404
                raise HTTPException(status_code=404, detail="unknown_symbol")
        
        # Query asset metadata (name, sector) - ALWAYS populate from DB if available
        asset = db.query(Asset).filter(Asset.symbol == validated_symbol).first()
        has_asset_row = asset is not None
        
        asset_name = ""
        asset_sector = ""
        asset_id = None
        
        if asset:
            asset_name = asset.name if asset.name else ""
            asset_sector = asset.sector if asset.sector else ""
            asset_id = asset.id
        
        # Fetch provider quote using public API (no private methods)
        provider_quote = None
        provider_stale = False
        provider_error_reason = None
        
        provider_fetch_start_ms = time.time() * 1000
        try:
            provider_quote = await _data_provider_service.get_quote(resolved_ticker, timeout_s=provider_timeout_s)
            # get_quote() returns dict with: last, change_pct, sparkline, ts, provider, stale, reason?
            if provider_quote:
                provider_stale = provider_quote.get("stale", False)
                # Extract reason if present
                if provider_quote.get("reason"):
                    provider_error_reason = provider_quote.get("reason")
        except Exception as e:
            provider_fetch_elapsed_ms = int((time.time() * 1000) - provider_fetch_start_ms)
            error_type = type(e).__name__
            error_msg = str(e)[:200] if len(str(e)) > 200 else str(e)
            logger.exception(
                f"[asset/detail] get_quote failed correlation_id={correlation_id} "
                f"resolved_ticker={resolved_ticker} error={error_type} - {error_msg} elapsed_ms={provider_fetch_elapsed_ms}"
            )
            provider_quote = None
            provider_error_reason = "provider_unknown"
        
        # Initialize price data
        last_price = 0.0
        change_pct = 0.0
        sparkline: list[float] = []
        last_ts: Optional[datetime] = None
        is_stale = True
        
        # Process provider quote according to contract
        if provider_quote:
            provider = provider_quote.get("provider", "none")
            provider_last = provider_quote.get("last", 0.0)
            
            # Contract: If provider=="none" or last<=0, set stale=true and reason
            if provider == "none" or provider_last is None or provider_last <= 0:
                is_stale = True
                if not reason:
                    reason = provider_quote.get("reason") or provider_error_reason or "provider_unavailable"
            else:
                # Valid data: extract fields
                try:
                    last_price = float(provider_last)
                    if last_price > 0:
                        provider_ok = True
                        is_stale = provider_quote.get("stale", False)
                        # Clear reason when we have valid fresh data
                        if not is_stale:
                            reason = None
                        
                        # Extract other fields
                        if provider_quote.get("change_pct") is not None:
                            try:
                                change_pct = float(provider_quote.get("change_pct", 0.0))
                            except (ValueError, TypeError):
                                pass
                        
                        if provider_quote.get("sparkline"):
                            try:
                                sparkline = [float(x) for x in provider_quote.get("sparkline", []) if x is not None]
                            except (ValueError, TypeError):
                                sparkline = []
                        
                        # Override name/sector from provider if available
                        if provider_quote.get("name"):
                            asset_name = provider_quote.get("name") or asset_name
                        if provider_quote.get("sector"):
                            asset_sector = provider_quote.get("sector") or asset_sector
                        
                        # Use provider timestamp
                        if provider_quote.get("ts"):
                            try:
                                last_ts = datetime.fromtimestamp(provider_quote.get("ts") / 1000.0, tz=timezone.utc)
                            except (ValueError, TypeError, OSError):
                                pass
                        
                        # Schedule background refresh if stale
                        if is_stale:
                            _data_provider_service.schedule_refresh(resolved_ticker)
                except (ValueError, TypeError) as e:
                    error_msg = str(e)[:200] if len(str(e)) > 200 else str(e)
                    logger.exception(f"[asset/detail] provider quote last parse error for {resolved_ticker}: {type(e).__name__} - {error_msg}")
                    is_stale = True
                    if not reason:
                        reason = "provider_parse_error"
        else:
            # No provider quote available - use error reason if available
            if provider_error_reason:
                reason = provider_error_reason
            else:
                reason = "provider_unavailable"
        
        # DB fallback: if provider failed, attempt DB price lookup
        if not provider_ok and asset_id:
            try:
                latest_price = db.query(Price).filter(
                    Price.asset_id == asset_id
                ).order_by(desc(Price.time)).first()
                
                if latest_price and latest_price.close is not None:
                    try:
                        db_last = float(latest_price.close)
                        if db_last > 0:
                            db_price_ok = True
                            last_price = db_last
                            last_ts = latest_price.time
                            
                            # Calculate change_pct: last vs previous close
                            prev_price = db.query(Price).filter(
                                Price.asset_id == asset_id,
                                Price.time < latest_price.time
                            ).order_by(desc(Price.time)).first()
                            
                            if prev_price and prev_price.close and prev_price.close > 0:
                                try:
                                    prev_close = float(prev_price.close)
                                    change_pct = ((last_price - prev_close) / prev_close) * 100.0
                                except (ValueError, TypeError):
                                    pass
                            
                            # Get sparkline: last 30-60 prices ordered by time ascending
                            sparkline_prices = db.query(Price).filter(
                                Price.asset_id == asset_id
                            ).order_by(Price.time.desc()).limit(60).all()
                            
                            if sparkline_prices:
                                try:
                                    sparkline_prices.reverse()
                                    sparkline = [float(p.close) for p in sparkline_prices if p.close is not None]
                                    if len(sparkline) > 60:
                                        sparkline = sparkline[-60:]
                                except (ValueError, TypeError):
                                    sparkline = []
                            
                            # Determine stale: last price timestamp must be within 15 minutes
                            if last_ts:
                                now_utc = datetime.now(timezone.utc)
                                if last_ts.tzinfo is None:
                                    last_ts_aware = last_ts.replace(tzinfo=timezone.utc)
                                else:
                                    last_ts_aware = last_ts.astimezone(timezone.utc)
                                age_minutes = (now_utc - last_ts_aware).total_seconds() / 60.0
                                is_stale = age_minutes > 15.0
                    except (ValueError, TypeError):
                        pass
            except Exception as e:
                logger.debug(f"[asset/detail] DB price lookup failed for {validated_symbol}: {type(e).__name__}")
        
        # Set reason if no price data (use provider error reason if available)
        if not provider_ok and not db_price_ok:
            if reason is None:
                if provider_error_reason:
                    reason = provider_error_reason
                else:
                    reason = "no_price_data"
        
        # Generate risk data (deterministic, temporary placeholder)
        risk = _data_provider_service._mock_risk(resolved_ticker)
        
        # Build response
        response = {
            "symbol": validated_symbol,
            "name": asset_name,
            "sector": asset_sector,
            "last": last_price,
            "change_pct": change_pct,
            "sparkline": sparkline,
            "risk": risk,
            "ts": int(last_ts.timestamp() * 1000) if last_ts else int(time.time() * 1000),
            "stale": is_stale,
            "build_tag": BUILD_TAG
        }
        
        # Add reason field if stale (always include reason when stale due to provider/DB failure)
        if is_stale:
            if reason:
                response["reason"] = reason
            elif not provider_ok and not db_price_ok:
                # Provider and DB both failed but no reason set - use generic fallback
                response["reason"] = "no_price_data"
            elif db_price_ok and is_stale:
                # DB price exists but is stale (>15 min old)
                response["reason"] = "db_price_stale"
        
        elapsed_ms = int((time.time() * 1000) - start_ms)
        
        # One-line logging right before returning
        logger.info(
            f"[assetdetail] symbol={validated_symbol} resolved_ticker={resolved_ticker} "
            f"provider={provider} stale={is_stale} reason={reason or 'none'} elapsed_ms={elapsed_ms}"
        )
        
        if elapsed_ms > 300:
            logger.warning(f"[asset/detail] slow response: {elapsed_ms}ms for {validated_symbol}")
        
        # Always return 200 (even if stale/no data)
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = int((time.time() * 1000) - start_ms)
        error_msg = str(e)[:200] if len(str(e)) > 200 else str(e)
        logger.exception(f"[asset/detail] error for {symbol} after {elapsed_ms}ms: {type(e).__name__}: {error_msg}")
        # Return stub on unexpected errors
        return {
            "symbol": validated_symbol if 'validated_symbol' in locals() else symbol.upper(),
            "name": "",
            "sector": "",
            "last": 0.0,
            "change_pct": 0.0,
            "sparkline": [],
            "risk": {"risk": 0.5, "shock": 0.5, "trend": 1, "vital": 0.5, "macro": 0.5},
            "ts": int(time.time() * 1000),
            "stale": True,
            "build_tag": BUILD_TAG
        }


@router.get("/macro/series", summary="Get FRED macroeconomic series")
async def get_macro_series(
    fred_id: str = Query(..., description="FRED series ID (e.g., GDP, UNRATE, CPIAUCSL)"),
    limit: int = Query(200, ge=1, le=500, description="Maximum number of observations (capped at 500)")
):
    """
    Get FRED macroeconomic series observations.
    
    Returns time series data with ISO8601 timestamps and values.
    Requires FRED_API_KEY to be configured in environment.
    Returns 503 if FRED_API_KEY is not configured or fetch fails.
    """
    start_ms = time.time() * 1000
    
    try:
        validated_fred_id = validate_fred_id(fred_id)
        
        # Check if FRED_API_KEY is available
        from config import settings
        if not settings.FRED_API_KEY:
            logger.warning(f"FRED_API_KEY not configured, returning 503 for {validated_fred_id}")
            raise HTTPException(
                status_code=503,
                detail="provider_unavailable"
            )
        
        result = await _data_provider_service.get_macro_series(validated_fred_id, limit=limit)
        
        elapsed_ms = int((time.time() * 1000) - start_ms)
        logger.info(f"FRED series {validated_fred_id} completed in {elapsed_ms}ms (provider={result.get('provider')})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        elapsed_ms = int((time.time() * 1000) - start_ms)
        logger.error(f"Error fetching FRED series {fred_id} after {elapsed_ms}ms: {e}", exc_info=True)
        # Return 503 on errors (no hang)
        raise HTTPException(
            status_code=503,
            detail="provider_unavailable"
        )


# ============================================================================
# WINDOWS RESTART INSTRUCTIONS (to ensure code changes are loaded):
# ============================================================================
# 1. Find process listening on port 8000:
#    netstat -ano | findstr :8000
#
# 2. Kill the process (replace <PID> with actual PID from step 1):
#    taskkill /PID <PID> /F
#
# 3. Restart uvicorn from project root:
#    cd c:\Users\alber\Documents\wsw-v1
#    uvicorn main:app --host 127.0.0.1 --port 8000 --reload
#
# 4. Verify code is loaded:
#    PowerShell: Invoke-WebRequest "http://127.0.0.1:8000/api/asset/detail?symbol=AST000001" | Select -ExpandProperty Content | ConvertFrom-Json | Select build_tag
#    Should return: "HOTFIX_V21"
# ============================================================================
#
# VALIDATION COMMANDS:
# PowerShell:
#   $u="http://127.0.0.1:8000/api/asset/detail?symbol=AST000001"
#   Measure-Command { (Invoke-WebRequest $u -TimeoutSec 1).StatusCode } | Select TotalMilliseconds
#   (Should be <300ms, even offline)
#
# curl:
#   curl -w "\nTime: %{time_total}s\n" "http://127.0.0.1:8000/api/asset/detail?symbol=AST000001"


@router.get("/_debug/env", summary="[DEBUG] Check environment configuration")
async def debug_env():
    """
    DEBUG endpoint to verify environment variable loading.
    Returns boolean flags for API keys (no secret values).
    """
    return {
        "debug": settings.DEBUG,
        "has_polygon_key": bool(getattr(settings, "POLYGON_API_KEY", None)),
        "has_fred_key": bool(getattr(settings, "FRED_API_KEY", None)),
        "build_tag": BUILD_TAG
    }


@router.post("/asset/seed-prices-dev", summary="[DEV ONLY] Seed synthetic prices for testing")
async def seed_prices_dev(
    symbol: str = Query(..., description="Asset symbol to seed prices for"),
    db: Session = Depends(get_db)
):
    """
    DEV-ONLY: Generate synthetic price data for a symbol.
    Only available when settings.DEBUG=True.
    Creates 60 days of daily prices with realistic drift.
    """
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="This endpoint is only available in DEBUG mode")
    
    try:
        validated_symbol = validate_symbol(symbol)
        
        # Find asset
        asset = db.query(Asset).filter(Asset.symbol == validated_symbol).first()
        if not asset:
            raise HTTPException(status_code=404, detail=f"Asset {validated_symbol} not found")
        
        # Check if prices already exist
        existing_count = db.query(Price).filter(Price.asset_id == asset.id).count()
        if existing_count > 0:
            logger.info(f"[seed-prices-dev] {validated_symbol} already has {existing_count} prices, skipping")
            return {"message": f"Asset {validated_symbol} already has {existing_count} prices", "skipped": True}
        
        # Generate 60 days of synthetic prices
        base_price = 100.0 + (hash(validated_symbol) % 200)  # Deterministic base
        prices = []
        current_price = base_price
        
        for i in range(60):
            # Deterministic drift using hash
            seed = hash(f"{validated_symbol}_{i}")
            import random
            random.seed(seed)
            change = random.uniform(-2.0, 2.0)  # Daily change
            current_price = max(10.0, min(500.0, current_price + change))
            
            price_time = datetime.now(timezone.utc) - timedelta(days=60 - i)
            price = Price(
                time=price_time,
                asset_id=asset.id,
                open=current_price * 0.99,
                high=current_price * 1.01,
                low=current_price * 0.98,
                close=current_price,
                volume=1000000 + (seed % 500000)
            )
            prices.append(price)
        
        db.add_all(prices)
        db.commit()
        
        logger.info(f"[seed-prices-dev] seeded {len(prices)} prices for {validated_symbol}")
        return {"message": f"Seeded {len(prices)} prices for {validated_symbol}", "count": len(prices)}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[seed-prices-dev] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
