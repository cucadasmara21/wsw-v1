"""
Resilient data provider service for asset details and macro series.
Uses async with strict timeouts to prevent hanging.
"""
import logging
import re
import hashlib
import time
import asyncio
from typing import Optional, Dict, List, Any, Tuple, Union
from cachetools import TTLCache

from config import settings

# Note: asyncio.Lock() is not thread-safe across threads, but we're in async context
# For thread-safe access, we use asyncio.Lock() which is safe within the same event loop

logger = logging.getLogger(__name__)

# Liquid tickers for AST\d+ resolution (~50 tickers)
LIQUID_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "GOOGL", "GOOG", "JPM",
    "XOM", "V", "JNJ", "WMT", "MA", "PG", "UNH", "HD", "DIS", "BAC", "AVGO",
    "CVX", "ABBV", "PFE", "KO", "COST", "MRK", "PEP", "TMO", "MCD", "CSCO",
    "ABT", "ACN", "ADBE", "NFLX", "NKE", "AMD", "TXN", "CMCSA", "LIN", "PM",
    "HON", "QCOM", "INTU", "AMGN", "RTX", "LOW", "IBM", "GE", "GS", "CAT"
]


class ProviderError(Exception):
    """Custom exception for provider failures"""
    pass


class DataProviderService:
    """Service for fetching asset details and macro series with strict timeouts and caching."""
    
    def __init__(self):
        # In-memory TTL caches
        self.fresh_cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=1000, ttl=15)  # 15s TTL (fresh)
        self.stale_cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=1000, ttl=600)  # 10m TTL (stale)
        self.macro_cache: TTLCache[str, Dict[str, Any]] = TTLCache(maxsize=100, ttl=300)  # 5m TTL
        
        # Concurrency controls for background refresh
        self.inflight: Dict[str, asyncio.Task] = {}  # Singleflight per ticker
        self.refresh_semaphore: Optional[asyncio.Semaphore] = None  # Max 4 concurrent refreshes (created lazily)
        self.circuit_breaker_until: Dict[str, float] = {}  # Per-ticker circuit breaker (timestamp)
        self._inflight_lock: Optional[asyncio.Lock] = None  # Async lock (created lazily)
    
    def resolve_ticker(self, symbol: str, db_session=None) -> Optional[str]:
        """
        Resolve symbol to provider ticker. AST\\d+ is handled FIRST with DB-first lookup.
        Never returns an AST* string as ticker; yfinance must not receive AST*.
        """
        # Handle AST\\d+ FIRST — DB-first lookup (absolute truth)
        if re.match(r'^AST\d+$', symbol):
            if db_session is not None:
                try:
                    from models import Asset
                    asset = db_session.query(Asset).filter(Asset.symbol == symbol).first()
                    if asset:
                        if hasattr(asset, 'ticker') and asset.ticker:
                            ticker = str(asset.ticker).upper()
                            logger.debug(f"[resolve_ticker] AST* {symbol} -> DB ticker column: {ticker}")
                            return ticker
                        if hasattr(asset, 'metadata_') and asset.metadata_:
                            t = asset.metadata_.get('ticker')
                            if t:
                                ticker = str(t).upper()
                                logger.debug(f"[resolve_ticker] AST* {symbol} -> DB metadata ticker: {ticker}")
                                return ticker
                except Exception as e:
                    logger.debug(f"[resolve_ticker] DB lookup for ticker failed for {symbol}: {type(e).__name__}: {e}")
            
            # Fallback: deterministic modulo mapping (synthetic)
            num = int(symbol[3:])
            ticker_index = num % len(LIQUID_TICKERS)
            ticker = LIQUID_TICKERS[ticker_index]
            logger.debug(f"[resolve_ticker] AST* {symbol} -> synthetic mapping (modulo): {ticker}")
            return ticker

        # Real ticker patterns: alphanumeric, may include dash/equals (e.g. BTC-USD, EURUSD=X)
        if re.match(r'^[A-Za-z0-9]+([\-=][A-Za-z0-9]+)?$', symbol):
            return symbol.strip().upper()

        return None
    
    def _mock_risk(self, ticker: str) -> Dict[str, float]:
        """
        Generate deterministic mock risk data from ticker hash.
        Returns stable values for the same ticker.
        """
        # Create stable hash from ticker
        hash_obj = hashlib.md5(ticker.encode())
        hash_int = int(hash_obj.hexdigest()[:8], 16)
        
        # Generate deterministic values in [0, 1] range
        risk = (hash_int % 1000) / 1000.0
        shock = ((hash_int // 1000) % 1000) / 1000.0
        vital = ((hash_int // 1000000) % 1000) / 1000.0
        macro = ((hash_int // 1000000000) % 1000) / 1000.0
        
        # Trend: 0 (flat), 1 (bull), 2 (bear)
        trend = hash_int % 3
        
        return {
            "risk": risk,
            "shock": shock,
            "trend": trend,
            "vital": vital,
            "macro": macro
        }
    
    async def _polygon_snapshot(self, ticker: str) -> Tuple[Optional[Tuple[Optional[float], Optional[float], Optional[str], Optional[str], Optional[str]]], Optional[str]]:
        """
        Fetch Polygon snapshot for ticker with strict timeout (0.5s total).
        Returns: ((last, change_pct, currency, name, sector), reason_code) or (None, reason_code) on failure.
        Reason codes: provider_timeout, provider_auth, provider_rate_limited, provider_network, provider_parse, provider_unavailable
        """
        # Check DISABLE_POLYGON flag (default True)
        if settings.DISABLE_POLYGON or not settings.POLYGON_API_KEY:
            return (None, "provider_unavailable")
        
        start_ms = time.time() * 1000
        try:
            import httpx
            
            url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}"
            params = {"apiKey": settings.POLYGON_API_KEY}
            
            # Strict timeout: 0.5s total (connect + read)
            timeout = httpx.Timeout(0.5, connect=0.2)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                elapsed_ms = int((time.time() * 1000) - start_ms)
                
                # Log HTTP response details for diagnostics
                response_body_preview = ""
                try:
                    response_text = response.text
                    response_body_preview = response_text[:200] if response_text else ""
                except Exception:
                    pass
                
                logger.info(f"[Polygon] HTTP {response.status_code} for {ticker} (elapsed={elapsed_ms}ms) URL={url} body_preview={response_body_preview}")
                
                # Handle specific status codes
                if response.status_code == 401 or response.status_code == 403:
                    logger.exception(f"[Polygon] auth failed for {ticker}: HTTP {response.status_code} (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                    return (None, "provider_auth")
                
                if response.status_code == 429:
                    logger.exception(f"[Polygon] rate limited for {ticker}: HTTP 429 (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                    return (None, "provider_rate_limited")
                
                if response.status_code >= 500:
                    logger.exception(f"[Polygon] server error for {ticker}: HTTP {response.status_code} (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                    return (None, "provider_network")
                
                # Non-200 status codes (but not 401/403/429/5xx) are HTTP errors
                if response.status_code != 200:
                    logger.exception(f"[Polygon] HTTP error for {ticker}: HTTP {response.status_code} (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                    return (None, "provider_http_error")
                
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "OK" and "ticker" in data:
                    ticker_data = data["ticker"]
                    day_data = ticker_data.get("day", {})
                    prev_day_data = ticker_data.get("prevDay", {})
                    
                    last = day_data.get("c")  # current close
                    prev_close = prev_day_data.get("c")  # previous day close
                    change_pct = None
                    
                    if last is not None and prev_close is not None and prev_close > 0:
                        change_pct = ((last - prev_close) / prev_close) * 100.0
                    
                    return (
                        (
                            float(last) if last is not None else None,
                            change_pct,
                            None,  # currency
                            None,  # name
                            None   # sector
                        ),
                        None  # success, no reason
                    )
                else:
                    logger.exception(f"[Polygon] invalid response for {ticker}: status={data.get('status')} (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                    return (None, "provider_parse")
                    
        except asyncio.TimeoutError:
            elapsed_ms = int((time.time() * 1000) - start_ms)
            logger.exception(f"[Polygon] timeout for {ticker} (elapsed={elapsed_ms}ms) URL={url}")
            return (None, "provider_timeout")
        except httpx.ConnectError as e:
            elapsed_ms = int((time.time() * 1000) - start_ms)
            logger.exception(f"[Polygon] connection error for {ticker}: {type(e).__name__} - {str(e)[:200]} (elapsed={elapsed_ms}ms) URL={url}")
            return (None, "provider_network")
        except httpx.HTTPStatusError as e:
            elapsed_ms = int((time.time() * 1000) - start_ms)
            status = e.response.status_code
            response_body_preview = ""
            try:
                response_text = e.response.text
                response_body_preview = response_text[:200] if response_text else ""
            except Exception:
                pass
            
            if status == 401 or status == 403:
                logger.exception(f"[Polygon] auth failed for {ticker}: HTTP {status} (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                return (None, "provider_auth")
            elif status == 429:
                logger.exception(f"[Polygon] rate limited for {ticker}: HTTP 429 (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                return (None, "provider_rate_limited")
            else:
                logger.exception(f"[Polygon] HTTP error for {ticker}: HTTP {status} (elapsed={elapsed_ms}ms) URL={url} body={response_body_preview}")
                return (None, "provider_network")
        except Exception as e:
            elapsed_ms = int((time.time() * 1000) - start_ms)
            logger.exception(f"[Polygon] exception for {ticker}: {type(e).__name__} - {str(e)[:200]} (elapsed={elapsed_ms}ms) URL={url}")
            return (None, "provider_unknown")
        
        return (None, "provider_unavailable")
    
    def _yfinance_sync(self, ticker: str) -> Tuple[Optional[Tuple[Optional[float], Optional[float], Optional[str], List[float], Optional[str], Optional[str]]], Optional[str]]:
        """
        Synchronous yfinance fetch (to be wrapped in asyncio.to_thread).
        Returns: ((last, change_pct, currency, sparkline, name, sector), reason_code) or (None, reason_code) on failure.
        Reason codes: provider_timeout, provider_network, provider_parse, provider_unavailable
        """
        start_ms = time.time() * 1000
        try:
            import yfinance as yf
        except ImportError:
            logger.warning("[yfinance] module not available")
            return (None, "provider_unavailable")

        # Never attempt yfinance downloads for AST* strings
        if re.match(r'^AST\d+$', ticker):
            logger.warning(f"[yfinance] refused AST* ticker {ticker}; use resolved ticker")
            return (None, "provider_parse")

        try:
            ticker_obj = yf.Ticker(ticker)
            
            # Try fast_info first for last price (with explicit timeout)
            last = None
            try:
                fast_info = ticker_obj.fast_info
                last = getattr(fast_info, 'lastPrice', None)
                if last is None:
                    last = getattr(fast_info, 'regularMarketPrice', None)
            except Exception as e:
                logger.debug(f"[yfinance] fast_info failed for {ticker}: {type(e).__name__}")
            
            # Get info for name, sector, currency
            info = {}
            try:
                info = ticker_obj.info
            except Exception as e:
                logger.debug(f"[yfinance] info fetch failed for {ticker}: {type(e).__name__}")
            
            name = info.get('longName') or info.get('shortName')
            sector = info.get('sector')
            currency = info.get('currency')
            
            # If no last price from fast_info, try history (with explicit timeout)
            if last is None:
                try:
                    hist = ticker_obj.history(period="1d", interval="1d", timeout=3)
                    if not hist.empty and len(hist) > 0:
                        # Try Close first, then Adj Close
                        if 'Close' in hist.columns:
                            close_val = hist['Close'].iloc[-1]
                            if close_val is not None and not (isinstance(close_val, float) and (close_val != close_val)):  # Check for NaN
                                last = float(close_val)
                        elif 'Adj Close' in hist.columns:
                            adj_close_val = hist['Adj Close'].iloc[-1]
                            if adj_close_val is not None and not (isinstance(adj_close_val, float) and (adj_close_val != adj_close_val)):
                                last = float(adj_close_val)
                        else:
                            logger.exception(f"[yfinance] history(1d) for {ticker}: DataFrame missing Close/Adj Close columns. Columns: {list(hist.columns)}")
                            return (None, "provider_parse_error")
                except KeyError as e:
                    logger.exception(f"[yfinance] history(1d) column error for {ticker}: {str(e)[:200]}")
                    return (None, "provider_parse_error")
                except Exception as e:
                    logger.exception(f"[yfinance] history(1d) failed for {ticker}: {type(e).__name__} - {str(e)[:200]}")
                    return (None, "provider_parse_error")
            
            # Calculate change_pct from history
            change_pct = None
            if last is not None and last > 0:
                try:
                    hist_2d = ticker_obj.history(period="2d", interval="1d", timeout=3)
                    if not hist_2d.empty and len(hist_2d) >= 2:
                        # Try Close first, then Adj Close
                        close_col = 'Close' if 'Close' in hist_2d.columns else ('Adj Close' if 'Adj Close' in hist_2d.columns else None)
                        if close_col:
                            prev_close_val = hist_2d[close_col].iloc[-2]
                            if prev_close_val is not None and not (isinstance(prev_close_val, float) and (prev_close_val != prev_close_val)):
                                prev_close = float(prev_close_val)
                                if prev_close > 0:
                                    change_pct = ((last - prev_close) / prev_close) * 100.0
                except KeyError as e:
                    logger.debug(f"[yfinance] history(2d) column error for {ticker}: {str(e)[:200]}")
                except Exception as e:
                    logger.debug(f"[yfinance] history(2d) failed for {ticker}: {type(e).__name__}")
            
            # Get sparkline: use 1mo 1d interval (faster than 5d 15m), downsample to 30-60 points max
            sparkline = []
            try:
                # Use 1mo 1d for faster fetch, then slice to last 30-60 points
                spark_hist = ticker_obj.history(period="1mo", interval="1d", timeout=3)
                if not spark_hist.empty and len(spark_hist) > 0:
                    # Try Close first, then Adj Close
                    close_col = 'Close' if 'Close' in spark_hist.columns else ('Adj Close' if 'Adj Close' in spark_hist.columns else None)
                    if close_col:
                        closes = spark_hist[close_col].tolist()
                        # Take last 30-60 points (keep small), filter out NaN/None
                        target_points = min(60, max(30, len(closes)))
                        if len(closes) > target_points:
                            closes = closes[-target_points:]
                        sparkline = [float(c) for c in closes if c is not None and not (isinstance(c, float) and (c != c))]
            except KeyError as e:
                logger.debug(f"[yfinance] sparkline column error for {ticker}: {str(e)[:200]}")
            except Exception as e:
                logger.debug(f"[yfinance] sparkline fetch failed for {ticker}: {type(e).__name__}")
            
            elapsed_ms = int((time.time() * 1000) - start_ms)
            if last is None or last <= 0:
                logger.exception(f"[yfinance] no valid price data for {ticker} (last={last}, elapsed={elapsed_ms}ms)")
                return (None, "provider_parse_error")
            
            return ((last, change_pct, currency, sparkline, name, sector), None)
        except Exception as e:
            elapsed_ms = int((time.time() * 1000) - start_ms)
            error_msg = str(e)[:200]
            logger.exception(f"[yfinance] exception for {ticker}: {type(e).__name__} - {error_msg} (elapsed={elapsed_ms}ms)")
            # Determine reason from exception type
            if "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                return (None, "provider_timeout")
            elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                return (None, "provider_network")
            else:
                return (None, "provider_unknown")
    
    async def _yfinance_quote_and_sparkline(self, ticker: str) -> Tuple[Optional[Tuple[Optional[float], Optional[float], Optional[str], List[float], Optional[str], Optional[str]]], Optional[str]]:
        """
        Fetch yfinance quote and sparkline data.
        Wraps blocking yfinance in asyncio.to_thread (non-blocking).
        Timeout is applied by the caller via asyncio.wait_for.
        Returns: ((last, change_pct, currency, sparkline, name, sector), reason_code) or (None, reason_code)
        """
        try:
            # Wrap blocking yfinance in thread (non-blocking, timeout applied by caller)
            result, reason = await asyncio.to_thread(self._yfinance_sync, ticker)
            return (result, reason)
        except Exception as e:
            logger.exception(f"[yfinance] async error for {ticker}: {type(e).__name__} - {str(e)[:200]}")
            return (None, "provider_unknown")
    
    def get_cached_quote(self, resolved_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get fresh cached quote (O(1), non-blocking).
        Returns None if not in fresh cache.
        """
        cache_key = resolved_ticker
        if cache_key in self.fresh_cache:
            return self.fresh_cache[cache_key]
        return None
    
    def get_stale_quote(self, resolved_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get stale cached quote (O(1), non-blocking).
        Returns None if not in stale cache.
        Adds stale flag and stale_age_ms.
        """
        cache_key = resolved_ticker
        if cache_key in self.stale_cache:
            stale_data = self.stale_cache[cache_key].copy()
            stale_ts = stale_data.get("ts", int(time.time() * 1000))
            stale_age_ms = int(time.time() * 1000) - stale_ts
            stale_data["stale"] = True
            stale_data["stale_age_ms"] = stale_age_ms
            return stale_data
        return None
    
    def schedule_refresh(self, resolved_ticker: str) -> None:
        """
        Schedule background refresh if not already inflight and circuit breaker allows.
        Non-blocking: creates task and returns immediately.
        """
        cache_key = resolved_ticker
        
        # Check circuit breaker (60s cooldown after failure)
        breaker_key = f"breaker:{cache_key}"
        if breaker_key in self.circuit_breaker_until:
            until_ts = self.circuit_breaker_until[breaker_key]
            if time.time() < until_ts:
                logger.debug(f"Circuit breaker open for {resolved_ticker}, skipping refresh")
                return
        
        # Check if already inflight (singleflight) and schedule if needed
        async def check_and_schedule():
            # Initialize locks lazily (first call in async context)
            if self._inflight_lock is None:
                self._inflight_lock = asyncio.Lock()
            if self.refresh_semaphore is None:
                self.refresh_semaphore = asyncio.Semaphore(4)
            
            async with self._inflight_lock:
                if cache_key in self.inflight:
                    task = self.inflight[cache_key]
                    if not task.done():
                        logger.debug(f"Refresh already inflight for {resolved_ticker}")
                        return
                    # Task done, clean up
                    del self.inflight[cache_key]
                
                # Create new refresh task
                task = asyncio.create_task(self._refresh_quote_async(cache_key))
                self.inflight[cache_key] = task
        
        # Schedule check (non-blocking)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(check_and_schedule())
            else:
                # No running loop, skip (should not happen in FastAPI context)
                pass
        except RuntimeError:
            # No event loop, skip (should not happen in FastAPI context)
            pass
    
    async def _refresh_quote_async(self, resolved_ticker: str) -> None:
        """
        Background refresh task: fetch from providers and update caches.
        Runs under semaphore to limit concurrency.
        Never blocks request path.
        """
        cache_key = resolved_ticker
        breaker_key = f"breaker:{cache_key}"
        
        # Initialize semaphore lazily if needed
        if self.refresh_semaphore is None:
            self.refresh_semaphore = asyncio.Semaphore(4)
        
        try:
            # Acquire semaphore (max 4 concurrent)
            async with self.refresh_semaphore:
                provider = "none"
                last = None
                change_pct = None
                sparkline: List[float] = []
                currency = None
                name = None
                sector = None
                fetch_succeeded = False
                
                provider_reason = None
                try:
                    # Try Polygon first (if available and not disabled) with strict timeout 0.5s
                    if settings.POLYGON_API_KEY and not settings.DISABLE_POLYGON:
                        try:
                            polygon_result, polygon_reason = await asyncio.wait_for(
                                self._polygon_snapshot(resolved_ticker),
                                timeout=0.5
                            )
                            if polygon_result:
                                provider = "polygon"
                                last, change_pct, currency, name, sector = polygon_result
                                fetch_succeeded = True
                            elif polygon_reason:
                                provider_reason = polygon_reason
                        except asyncio.TimeoutError:
                            logger.warning(f"[refresh] Polygon async timeout for {resolved_ticker}")
                            provider_reason = "provider_timeout"
                        except Exception as e:
                            logger.error(f"[refresh] Polygon async exception for {resolved_ticker}: {type(e).__name__} - {str(e)[:200]}", exc_info=True)
                            provider_reason = "provider_network"
                    
                    # Fallback to yfinance (budget: 0.8s)
                    if not fetch_succeeded:
                        try:
                            yfinance_result, yf_reason = await self._yfinance_quote_and_sparkline(resolved_ticker)
                            if yfinance_result:
                                provider = "yfinance"
                                yf_last, yf_change_pct, yf_currency, yf_sparkline, yf_name, yf_sector = yfinance_result
                                
                                # Merge yfinance data
                                if yf_sparkline:
                                    sparkline = yf_sparkline
                                if yf_currency:
                                    currency = yf_currency
                                if yf_name:
                                    name = yf_name
                                if yf_sector:
                                    sector = yf_sector
                                last = yf_last
                                change_pct = yf_change_pct
                                fetch_succeeded = True
                            elif yf_reason:
                                provider_reason = yf_reason
                        except Exception as e:
                            logger.error(f"[refresh] yfinance async exception for {resolved_ticker}: {type(e).__name__} - {str(e)[:200]}", exc_info=True)
                            provider_reason = "provider_network"
                    
                except Exception as e:
                    logger.error(f"[refresh] Provider fetch exception for {resolved_ticker}: {type(e).__name__} - {str(e)[:200]}", exc_info=True)
                    provider_reason = "provider_network"
                
                # If fetch succeeded, update both caches
                if fetch_succeeded and provider != "none":
                    result = {
                        "last": last,
                        "change_pct": change_pct,
                        "sparkline": sparkline,
                        "ts": int(time.time() * 1000),
                        "provider": provider,
                        "currency": currency,
                        "name": name,
                        "sector": sector,
                        "stale": False
                    }
                    # Update fresh cache (15s)
                    self.fresh_cache[cache_key] = result
                    # Update stale cache (10m)
                    self.stale_cache[cache_key] = result
                    # Clear circuit breaker on success
                    if breaker_key in self.circuit_breaker_until:
                        del self.circuit_breaker_until[breaker_key]
                    logger.debug(f"Background refresh succeeded for {resolved_ticker} (provider={provider})")
                else:
                    # Fetch failed: open circuit breaker for 60s
                    self.circuit_breaker_until[breaker_key] = time.time() + 60.0
                    logger.debug(f"Background refresh failed for {resolved_ticker}, circuit breaker open for 60s")
        
        except Exception as e:
            logger.debug(f"Background refresh task exception for {resolved_ticker}: {type(e).__name__}")
            # Open circuit breaker on exception
            self.circuit_breaker_until[breaker_key] = time.time() + 60.0
        finally:
            # Clean up inflight task
            if self._inflight_lock is not None:
                async with self._inflight_lock:
                    if cache_key in self.inflight:
                        del self.inflight[cache_key]
            else:
                # Fallback if lock not initialized (should not happen)
                if cache_key in self.inflight:
                    del self.inflight[cache_key]
    
    async def get_quote(self, resolved_ticker: str, timeout_s: float = 12.0) -> Dict[str, Any]:
        """
        Fetch quote with stale-while-revalidate pattern.
        Cache key MUST be resolved ticker (e.g., AAPL), not AST000001.
        Returns: { last, change_pct, sparkline, ts, provider, stale, reason? }
        Contract: If provider=="none" or last<=0, stale=true and reason is set.
        """
        cache_key = resolved_ticker
        
        # Check fresh cache first (15s TTL)
        if cache_key in self.fresh_cache:
            cached = self.fresh_cache[cache_key]
            logger.debug(f"Fresh cache hit for {resolved_ticker}")
            return cached
        
        # Attempt provider fetch with configurable timeout
        provider = "none"
        last = None
        change_pct = None
        sparkline: List[float] = []
        currency = None
        name = None
        sector = None
        fetch_reason = None
        fetch_succeeded = False
        
        try:
            # Try Polygon first (if available and not disabled) with timeout
            if settings.POLYGON_API_KEY and not settings.DISABLE_POLYGON:
                try:
                    polygon_result, polygon_reason = await asyncio.wait_for(
                        self._polygon_snapshot(resolved_ticker),
                        timeout=min(0.5, timeout_s * 0.4)
                    )
                    if polygon_result:
                        provider = "polygon"
                        last, change_pct, currency, name, sector = polygon_result
                        fetch_succeeded = True
                    elif polygon_reason:
                        fetch_reason = polygon_reason
                except asyncio.TimeoutError:
                    fetch_reason = "provider_timeout"
                except Exception as e:
                    logger.exception(f"[get_quote] Polygon exception for {resolved_ticker}: {type(e).__name__} - {str(e)[:200]}")
                    fetch_reason = "provider_unknown"
            
            # Fallback to yfinance if Polygon failed or not available
            if provider == "none" or (last is None or last <= 0):
                try:
                    yfinance_result, yf_reason = await asyncio.wait_for(
                        self._yfinance_quote_and_sparkline(resolved_ticker),
                        timeout=timeout_s
                    )
                    if yfinance_result:
                        if provider == "none":
                            provider = "yfinance"
                        yf_last, yf_change_pct, yf_currency, yf_sparkline, yf_name, yf_sector = yfinance_result
                        
                        # Merge yfinance data (it has more fields)
                        if yf_sparkline:
                            sparkline = yf_sparkline
                        if yf_currency:
                            currency = yf_currency
                        if yf_name:
                            name = yf_name
                        if yf_sector:
                            sector = yf_sector
                        # Use yfinance price if Polygon didn't provide it or it's invalid
                        if last is None or last <= 0:
                            last = yf_last
                        if change_pct is None:
                            change_pct = yf_change_pct
                        if last and last > 0:
                            fetch_succeeded = True
                    elif yf_reason:
                        if not fetch_reason:
                            fetch_reason = yf_reason
                except asyncio.TimeoutError:
                    if not fetch_reason:
                        fetch_reason = "provider_timeout"
                except Exception as e:
                    logger.exception(f"[get_quote] yfinance exception for {resolved_ticker}: {type(e).__name__} - {str(e)[:200]}")
                    if not fetch_reason:
                        fetch_reason = "provider_unknown"
                
        except Exception as e:
            logger.exception(f"[get_quote] Provider fetch exception for {resolved_ticker}: {type(e).__name__} - {str(e)[:200]}")
            if not fetch_reason:
                fetch_reason = "provider_unknown"
        
        # Build result according to contract: provider=="none" or last<=0 => stale=true with reason
        if fetch_succeeded and provider != "none" and last is not None and last > 0:
            result = {
                "last": float(last),
                "change_pct": float(change_pct) if change_pct is not None else 0.0,
                "sparkline": sparkline or [],
                "ts": int(time.time() * 1000),
                "provider": provider,
                "currency": currency,
                "name": name,
                "sector": sector,
                "stale": False
            }
            # Update fresh cache (15s)
            self.fresh_cache[cache_key] = result
            # Update stale cache (10m)
            self.stale_cache[cache_key] = result
            return result
        
        # If fetch failed, check stale cache
        if cache_key in self.stale_cache:
            stale_data = self.stale_cache[cache_key].copy()
            stale_ts = stale_data.get("ts", int(time.time() * 1000))
            stale_age_ms = int(time.time() * 1000) - stale_ts
            stale_data["stale"] = True
            stale_data["stale_age_ms"] = stale_age_ms
            if fetch_reason:
                stale_data["reason"] = fetch_reason
            logger.debug(f"Stale cache hit for {resolved_ticker} (age={stale_age_ms}ms)")
            return stale_data
        
        # No data: return placeholder with stale=true and reason (contract compliance)
        result = {
            "last": 0.0,
            "change_pct": 0.0,
            "sparkline": [],
            "ts": int(time.time() * 1000),
            "provider": "none",
            "currency": None,
            "name": None,
            "sector": None,
            "stale": True,
            "reason": fetch_reason or "provider_unavailable"
        }
        return result
    
    def get_stale_quote(self, resolved_ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get stale quote from cache (O(1) operation).
        Returns None if no stale cache exists.
        """
        cache_key = resolved_ticker
        if cache_key in self.stale_cache:
            stale_data = self.stale_cache[cache_key].copy()
            stale_ts = stale_data.get("ts", int(time.time() * 1000))
            stale_age_ms = int(time.time() * 1000) - stale_ts
            stale_data["stale"] = True
            stale_data["stale_age_ms"] = stale_age_ms
            return stale_data
        return None
    
    async def _fred_series(self, fred_id: str, limit: int) -> List[Dict[str, Any]]:
        """
        Fetch FRED series observations with strict timeout (1.0s).
        Returns list of {"t": ISO8601_date, "v": number|null}
        """
        if not settings.FRED_API_KEY:
            return []
        
        try:
            import httpx
            
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": fred_id,
                "api_key": settings.FRED_API_KEY,
                "file_type": "json",
                "limit": limit,
                "sort_order": "desc"  # Most recent first
            }
            
            # Strict timeout: 1.0s total
            timeout = httpx.Timeout(1.0, connect=0.3)
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                series = []
                if "observations" in data:
                    for obs in data["observations"]:
                        # Parse value (can be ".", which means missing)
                        value_str = obs.get("value", ".")
                        value = None
                        if value_str != ".":
                            try:
                                value = float(value_str)
                            except (ValueError, TypeError):
                                value = None
                        
                        # Parse date (ISO8601 format)
                        date_str = obs.get("date", "")
                        series.append({
                            "t": date_str,  # ISO8601 date string
                            "v": value
                        })
                
                # Reverse to chronological order (oldest first)
                series.reverse()
                return series
        except asyncio.TimeoutError:
            logger.debug(f"FRED timeout for {fred_id}")
            return []
        except Exception as e:
            logger.debug(f"FRED fetch failed for {fred_id}: {type(e).__name__}")
            return []
    
    async def get_macro_series(self, fred_id: str, limit: int = 200) -> Dict[str, Any]:
        """
        Fetch FRED macroeconomic series with caching.
        Returns dict with: fred_id, series, provider, ts
        """
        # Cap limit at 500
        limit = min(limit, 500)
        
        # Check cache first
        cache_key = f"fred:{fred_id}:{limit}"
        if cache_key in self.macro_cache:
            cached = self.macro_cache[cache_key]
            logger.debug(f"Cache hit for FRED {fred_id}")
            return cached
        
        # Fetch from FRED
        series = await self._fred_series(fred_id, limit)
        
        if series:
            provider = "fred"
        else:
            provider = "none"
        
        response_data = {
            "fred_id": fred_id,
            "series": series,
            "provider": provider,
            "ts": int(time.time() * 1000)
        }
        
        # Cache result
        self.macro_cache[cache_key] = response_data
        
        return response_data


# Module-level singleton instance
_data_provider_service = DataProviderService()
