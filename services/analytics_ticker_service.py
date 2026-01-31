"""
Background service that fetches prices and updates analytics signals.
Runs as a background task, updating the shared points buffer and broadcasting via WebSocket.
"""

import asyncio
import logging
from typing import Dict, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from analytics.engine import AnalyticsEngine
from services.points_buffer_service import get_points_buffer_service
from api.websocket import broadcast_diff

logger = logging.getLogger(__name__)


class AnalyticsTickerService:
    """
    Background service that:
    1. Fetches prices (yfinance stub or real data)
    2. Updates analytics engine (CUSUM/RLS/VPIN)
    3. Updates shared points buffer
    4. Broadcasts diffs via WebSocket
    """
    
    def __init__(self, tick_interval_ms: int = 1000):
        """
        Args:
            tick_interval_ms: Interval between price updates (default 1000ms = 1s)
        """
        self.tick_interval_ms = tick_interval_ms
        self.engine: Optional[AnalyticsEngine] = None
        self.running = False
        self.task: Optional[asyncio.Task] = None
        self.symbol_to_index: Dict[str, int] = {}
    
    async def initialize(self, db: Session):
        """Initialize analytics engine and symbol mappings."""
        try:
            # Get asset count and symbols from database
            rows = db.execute(
                text("""
                    SELECT id, symbol
                    FROM assets
                    ORDER BY id
                    LIMIT 100000
                """)
            ).fetchall()
            
            asset_count = len(rows)
            if asset_count == 0:
                logger.warning("No assets found for analytics ticker")
                return False
            
            # Build symbol -> index mapping
            self.symbol_to_index.clear()
            for idx, row in enumerate(rows):
                symbol = str(row.symbol) if row.symbol else f"ASSET-{row.id}"
                self.symbol_to_index[symbol] = idx
            
            # Initialize analytics engine
            self.engine = AnalyticsEngine(asset_count=asset_count, macro8=128)
            
            # Initialize buffer service
            buffer_service = get_points_buffer_service()
            if not buffer_service.is_initialized():
                buffer_service.initialize(db, limit=asset_count)
            
            logger.info(f"Analytics ticker initialized: {asset_count} assets")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize analytics ticker: {e}", exc_info=True)
            return False
    
    async def fetch_prices_stub(self, symbols: list[str]) -> Dict[str, float]:
        """
        Stub price fetcher (can be replaced with real yfinance/API calls).
        For now, generates deterministic prices based on symbol hash.
        """
        import hashlib
        import time
        
        prices = {}
        t = time.time()
        
        for symbol in symbols:
            # Generate deterministic price with small random walk
            h = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
            base_price = 100.0 + (h % 1000) / 10.0
            # Add small time-based variation
            variation = (t % 100) * 0.01
            prices[symbol] = base_price + variation
        
        return prices
    
    async def fetch_prices_yfinance(self, symbols: list[str]) -> Dict[str, float]:
        """
        Fetch prices using yfinance (if available).
        Falls back to stub if yfinance fails.
        """
        try:
            import yfinance as yf
            
            # Batch fetch (yfinance supports multiple symbols)
            tickers = yf.Tickers(" ".join(symbols[:50]))  # Limit to 50 at a time
            
            prices = {}
            for symbol in symbols[:50]:
                try:
                    ticker = tickers.tickers.get(symbol)
                    if ticker:
                        info = ticker.info
                        if 'regularMarketPrice' in info:
                            prices[symbol] = float(info['regularMarketPrice'])
                        elif 'currentPrice' in info:
                            prices[symbol] = float(info['currentPrice'])
                except Exception as e:
                    logger.debug(f"Failed to fetch {symbol}: {e}")
            
            if prices:
                return prices
            
        except ImportError:
            logger.debug("yfinance not available, using stub")
        except Exception as e:
            logger.debug(f"yfinance fetch failed: {e}")
        
        # Fallback to stub
        return await self.fetch_prices_stub(symbols)
    
    async def tick(self):
        """Execute one tick: fetch prices, update signals, broadcast."""
        if not self.engine:
            return
        
        try:
            # Fetch prices (use yfinance if available, else stub)
            symbols = list(self.symbol_to_index.keys())
            if not symbols:
                return
            
            # Fetch prices (try yfinance first, fallback to stub)
            prices = await self.fetch_prices_yfinance(symbols)
            
            # Update analytics engine
            updated_indices = self.engine.tick(
                prices=prices,
                asset_index_map=self.symbol_to_index,
                volumes=None  # Can be enhanced with volume data
            )
            
            if len(updated_indices) == 0:
                return
            
            # Build updates dict: index -> meta32
            updates = {}
            for idx in updated_indices:
                meta32 = self.engine.get_meta32(int(idx))
                updates[int(idx)] = meta32
            
            # Update shared buffer
            buffer_service = get_points_buffer_service()
            if buffer_service.is_initialized():
                buffer_service.update_batch(updates)
            
            # Broadcast via WebSocket
            await broadcast_diff(updates)
            
            if len(updates) > 0:
                logger.debug(f"Tick: updated {len(updates)} assets")
        
        except Exception as e:
            logger.error(f"Tick error: {e}", exc_info=True)
    
    async def run(self):
        """Main loop: run ticks at specified interval."""
        self.running = True
        logger.info(f"Analytics ticker started (interval={self.tick_interval_ms}ms)")
        
        while self.running:
            try:
                await self.tick()
            except Exception as e:
                logger.error(f"Tick loop error: {e}", exc_info=True)
            
            # Wait for next tick
            await asyncio.sleep(self.tick_interval_ms / 1000.0)
    
    def start(self):
        """Start the background task."""
        if self.task is not None and not self.task.done():
            logger.warning("Analytics ticker already running")
            return
        
        self.task = asyncio.create_task(self.run())
        logger.info("Analytics ticker task created")
    
    def stop(self):
        """Stop the background task."""
        self.running = False
        if self.task:
            self.task.cancel()
            logger.info("Analytics ticker stopped")


# Global singleton instance
_analytics_ticker_service = AnalyticsTickerService(tick_interval_ms=1000)


def get_analytics_ticker_service() -> AnalyticsTickerService:
    """Get the global analytics ticker service instance."""
    return _analytics_ticker_service
