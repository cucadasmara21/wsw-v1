#!/usr/bin/env python3
"""
Realtime Bridge: Redis PubSub / Postgres NOTIFY → Universe Updates
Processes price/asset updates in batches and updates universe_assets atomically.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Set, Optional
from collections import deque

# Add project root to path
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg required. Install: pip install asyncpg")
    sys.exit(1)

try:
    import redis.asyncio as redis
except ImportError:
    print("ERROR: redis required. Install: pip install redis")
    sys.exit(1)

try:
    from config import settings
    from backend.models.universe import VertexLayout28, pack_taxonomy32, pack_meta32
except ImportError as e:
    print(f"ERROR: Failed to import required modules: {e}")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Batch configuration
# P-03: Deterministic real-time budget (work_cap per tick)
from engines.constants import WORK_CAP_PER_TICK
BATCH_SIZE = 256
BATCH_INTERVAL_MS = 10
MAX_QUEUE_SIZE = 100_000  # Bounded; excess deferred to next tick


class RealtimeBridge:
    """Bridge between Redis/Postgres notifications and universe_assets updates"""
    
    def __init__(self, dsn: str, redis_url: Optional[str] = None):
        self.dsn = dsn
        self.redis_url = redis_url
        self.pg_conn: Optional[asyncpg.Connection] = None
        self.redis_client: Optional[redis.Redis] = None
        self.update_queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.running = False
        
    async def start(self):
        """Start the bridge"""
        logger.info("Starting RealtimeBridge...")
        
        # Connect to Postgres
        self.pg_conn = await asyncpg.connect(self.dsn)
        logger.info("Connected to PostgreSQL")
        
        # Connect to Redis if URL provided
        if self.redis_url:
            try:
                self.redis_client = redis.from_url(self.redis_url)
                await self.redis_client.ping()
                logger.info(f"Connected to Redis: {self.redis_url}")
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}, continuing without Redis")
                self.redis_client = None
        
        self.running = True
        
        # Start tasks
        tasks = [
            asyncio.create_task(self.listen_postgres()),
            asyncio.create_task(self.listen_redis()),
            asyncio.create_task(self.process_batches()),
        ]
        
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Bridge stopped")
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the bridge"""
        self.running = False
        if self.pg_conn:
            await self.pg_conn.close()
        if self.redis_client:
            await self.redis_client.close()
        logger.info("Bridge stopped")
    
    async def listen_postgres(self):
        """Listen to Postgres NOTIFY events"""
        if not self.pg_conn:
            return
        
        try:
            await self.pg_conn.add_listener('price_update', self._handle_pg_notify)
            logger.info("Listening to Postgres NOTIFY 'price_update'")
            
            # Keep alive
            while self.running:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Postgres listener error: {e}")
    
    def _handle_pg_notify(self, connection, pid, channel, payload):
        """Handle Postgres NOTIFY event"""
        try:
            asset_id = payload.strip()
            asyncio.create_task(self._enqueue_update(asset_id))
        except Exception as e:
            logger.error(f"Error handling pg_notify: {e}")
    
    async def listen_redis(self):
        """Listen to Redis PubSub"""
        if not self.redis_client:
            return
        
        try:
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe('price_update', 'asset_update')
            logger.info("Listening to Redis channels: price_update, asset_update")
            
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    channel = message['channel'].decode()
                    payload = message['data'].decode()
                    await self._enqueue_update(payload)
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
    
    async def _enqueue_update(self, asset_id: str):
        """Enqueue asset update"""
        try:
            self.update_queue.put_nowait(asset_id)
        except asyncio.QueueFull:
            logger.warning(f"Update queue full, dropping asset_id: {asset_id}")
    
    async def process_batches(self):
        """Process updates in batches. P-03: work_cap=50k per tick; excess deferred."""
        batch: Set[str] = set()
        last_batch_time = asyncio.get_event_loop().time()
        
        while self.running:
            try:
                timeout = BATCH_INTERVAL_MS / 1000.0
                deadline = last_batch_time + timeout
                
                # P-03: Collect at most WORK_CAP_PER_TICK per tick (bounded)
                while len(batch) < WORK_CAP_PER_TICK:
                    remaining = deadline - asyncio.get_event_loop().time()
                    if remaining <= 0:
                        break
                    
                    try:
                        asset_id = await asyncio.wait_for(
                            self.update_queue.get(),
                            timeout=min(remaining, 0.01)
                        )
                        batch.add(asset_id)
                    except asyncio.TimeoutError:
                        break
                
                # Process batch if ready (at least BATCH_SIZE or timeout)
                if batch and (len(batch) >= BATCH_SIZE or
                              (asyncio.get_event_loop().time() - last_batch_time) >= timeout):
                    await self._process_batch(batch)
                    batch.clear()
                    last_batch_time = asyncio.get_event_loop().time()
                
                await asyncio.sleep(0.001)
                
            except Exception as e:
                logger.error(f"Batch processing error: {e}")
                await asyncio.sleep(0.1)
    
    async def _process_batch(self, asset_ids: Set[str]):
        """Process a batch of asset updates"""
        if not asset_ids or not self.pg_conn:
            return
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            # Fetch legacy data for updated assets
            asset_list = list(asset_ids)
            rows = await self.pg_conn.fetch("""
                SELECT
                    sa.asset_id,
                    sa.symbol,
                    sa.sector,
                    COALESCE(sa.x, 0.0) AS x,
                    COALESCE(sa.y, 0.0) AS y,
                    COALESCE(sa.z, 0.0) AS z,
                    EXISTS(SELECT 1 FROM prices WHERE asset_id = sa.asset_id LIMIT 1) AS has_price
                FROM source_assets sa
                WHERE sa.asset_id::text = ANY($1)
            """, asset_list)
            
            if not rows:
                return
            
            # Create staging table
            staging_table = "staging_universe_realtime"
            await self.pg_conn.execute(f"""
                CREATE TEMP TABLE {staging_table} (
                    symbol TEXT NOT NULL,
                    morton_code BIGINT NOT NULL,
                    taxonomy32 INTEGER NOT NULL,
                    meta32 INTEGER NOT NULL,
                    x FLOAT NOT NULL,
                    y FLOAT NOT NULL,
                    z FLOAT NOT NULL,
                    fidelity_score FLOAT NOT NULL,
                    vertex_buffer BYTEA NOT NULL
                )
            """)
            
            # Process rows (reuse logic from seed script)
            import hashlib
            staging_records = []
            
            for row in rows:
                symbol = str(row['symbol'])
                sector = str(row['sector']) if row['sector'] else 'TECH'
                
                # Map sector to ID
                sector_map = {'TECH': 1, 'FIN': 2, 'HLTH': 3, 'ENER': 4,
                             'INDS': 5, 'COMM': 6, 'MATR': 7, 'UTIL': 8}
                sector_id = sector_map.get(sector, 1)
                
                # Coordinates
                x = max(0.0, min(1.0, float(row['x'])))
                y = max(0.0, min(1.0, float(row['y'])))
                z = max(0.0, min(1.0, float(row['z'])))
                
                if x == 0.0 and y == 0.0 and z == 0.0:
                    h = hashlib.sha256(symbol.encode()).digest()
                    x = (int.from_bytes(h[0:4], 'big') % 10000) / 10000.0
                    y = (int.from_bytes(h[4:8], 'big') % 10000) / 10000.0
                    z = (int.from_bytes(h[8:12], 'big') % 10000) / 10000.0
                
                # Compute fields (simplified - reuse from seed script)
                morton_code = int(hashlib.sha256(symbol.encode()).hexdigest()[:15], 16) & 0x7FFFFFFFFFFFFFFF
                industry = (int(hashlib.md5(symbol.encode()).hexdigest()[:2], 16) % 63) + 1
                risk_tier = (int(hashlib.md5(symbol.encode()).hexdigest()[3], 16) % 7) + 1
                volatility = (int(hashlib.md5(symbol.encode()).hexdigest()[4], 16) % 31) + 1
                
                taxonomy32 = (
                    (sector_id & 0xF) << 28 |
                    (industry & 0x3F) << 22 |
                    (risk_tier & 0x7) << 19 |
                    (volatility & 0x1F) << 14 |
                    1  # reserved
                ) & 0xFFFFFFFF
                
                outlier = (hashlib.md5(symbol.encode()).hexdigest()[0] in '012345')
                liquidity_tier = (int(hashlib.md5(symbol.encode()).hexdigest()[2], 16) % 3) + 1
                meta32 = pack_meta32(
                    min(255, max(1, risk_tier * 32)),
                    128 if outlier else 0,
                    1,
                    min(63, max(1, liquidity_tier * 8)),
                    0
                )
                
                has_price = bool(row['has_price'])
                fidelity = 0.90 if has_price else 0.60
                spin = (bin(taxonomy32).count('1') % 2) * 0.5
                
                vertex_buffer = VertexLayout28.pack_vertex_record(
                    taxonomy32, meta32, x, y, z, fidelity, spin
                )
                
                staging_records.append((
                    symbol, morton_code, taxonomy32, meta32,
                    x, y, z, fidelity, vertex_buffer
                ))
            
            # COPY to staging
            await self.pg_conn.copy_records_to_table(
                staging_table,
                records=staging_records,
                columns=['symbol', 'morton_code', 'taxonomy32', 'meta32',
                        'x', 'y', 'z', 'fidelity_score', 'vertex_buffer']
            )
            
            # UPSERT
            await self.pg_conn.execute(f"""
                INSERT INTO universe_assets (
                    symbol, morton_code, taxonomy32, meta32,
                    x, y, z, fidelity_score, vertex_buffer,
                    governance_status
                )
                SELECT
                    symbol, morton_code, taxonomy32, meta32,
                    x, y, z, fidelity_score, vertex_buffer,
                    'PROVISIONAL'
                FROM {staging_table}
                ON CONFLICT (symbol) DO UPDATE SET
                    morton_code = EXCLUDED.morton_code,
                    taxonomy32 = EXCLUDED.taxonomy32,
                    meta32 = EXCLUDED.meta32,
                    x = EXCLUDED.x,
                    y = EXCLUDED.y,
                    z = EXCLUDED.z,
                    fidelity_score = EXCLUDED.fidelity_score,
                    vertex_buffer = EXCLUDED.vertex_buffer,
                    last_quantum_update = NOW()
            """)
            
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            logger.info(f"Processed batch: {len(staging_records)} assets in {elapsed:.1f}ms")
            
            # Notify completion
            await self.pg_conn.execute("SELECT pg_notify('universe_delta_ready', $1)", str(len(staging_records)))
            
        except Exception as e:
            logger.error(f"Error processing batch: {e}", exc_info=True)


async def main():
    """Main entry point"""
    dsn = settings.DATABASE_DSN_ASYNC or settings.normalize_async_dsn(settings.DATABASE_URL)
    
    if not dsn or dsn.startswith('sqlite'):
        logger.error("ERROR: DATABASE_DSN_ASYNC must be a PostgreSQL connection string")
        sys.exit(1)
    
    bridge = RealtimeBridge(dsn, settings.REDIS_URL)
    
    try:
        await bridge.start()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await bridge.stop()


if __name__ == '__main__':
    asyncio.run(main())
