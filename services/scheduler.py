"""
Optional background scheduler for metrics recomputation and alert generation.

Only runs if ENABLE_SCHEDULER=true in environment.
Runs a lightweight asyncio loop to avoid blocking the event loop.
"""

import logging
import uuid
from datetime import datetime
import asyncio
from typing import Optional

from database import SessionLocal
from models import Asset, AssetMetricSnapshot, Alert
from services.metrics_registry import registry, CoreMetricsComputer
from services.alerts_service import AlertsService

logger = logging.getLogger(__name__)


class JobContext:
    """Context for a background job with request_id-like tracking"""

    def __init__(self, job_id: Optional[str] = None):
        self.job_id = job_id or f"job-{uuid.uuid4().hex[:8]}"

    def log(self, level: str, msg: str):
        """Log with job_id"""
        logger.log(getattr(logging, level.upper(), logging.INFO), f"[{self.job_id}] {msg}")


async def recompute_metrics_for_asset(asset_id: int, ctx: JobContext):
    """Recompute metrics for a single asset"""
    db = SessionLocal()
    try:
        ctx.log("info", f"Starting metrics recomputation for asset {asset_id}")

        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            ctx.log("warning", f"Asset {asset_id} not found")
            return

        # Get prices for this asset (simplified - in production, fetch recent N bars)
        from models import Price

        prices = (
            db.query(Price)
            .filter(Price.asset_id == asset_id)
            .order_by(Price.time.desc())
            .limit(252)
            .all()
        )

        if len(prices) < 20:
            ctx.log("warning", f"Insufficient data for asset {asset_id}: {len(prices)} bars")
            return

        # Convert to bars format
        bars = [
            {
                "close": p.close,
                "high": p.high or p.close,
                "low": p.low or p.close,
                "volume": p.volume or 0,
            }
            for p in reversed(prices)  # Oldest first
        ]

        # Compute metrics
        result = registry.compute(asset, bars, asset.category_id)

        # Save snapshot
        snapshot = AssetMetricSnapshot(
            asset_id=asset_id,
            as_of=datetime.utcnow(),
            metrics=result["metrics"],
            quality=result["quality"],
            explain=result["explain"],
        )
        db.add(snapshot)

        # Generate alerts
        AlertsService.generate_alerts(asset, result["metrics"], result["quality"], db)

        db.commit()
        ctx.log("info", f"Completed metrics recomputation for asset {asset_id}")

    except Exception as e:
        ctx.log("error", f"Error recomputing metrics for asset {asset_id}: {e}")
        db.rollback()
    finally:
        db.close()


async def recompute_all_active_assets(limit: int = 50, ctx: Optional[JobContext] = None):
    """Recompute metrics for all active assets (up to limit)"""
    if ctx is None:
        ctx = JobContext()

    db = SessionLocal()
    try:
        ctx.log("info", f"Starting batch metrics recomputation (limit={limit})")

        # Get active assets
        assets = (
            db.query(Asset)
            .filter(Asset.is_active == True)
            .limit(limit)
            .all()
        )

        ctx.log("info", f"Found {len(assets)} active assets to process")

        for asset in assets:
            await recompute_metrics_for_asset(asset.id, ctx)

        ctx.log("info", f"Batch metrics recomputation complete")

    except Exception as e:
        ctx.log("error", f"Error in batch recomputation: {e}")
    finally:
        db.close()


class Scheduler:
    """Simple scheduler for background jobs"""

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self.is_running = False

    async def start(self):
        """Start the scheduler (would need APScheduler or similar in production)"""
        if not self.enabled:
            logger.info("Scheduler disabled")
            return

        self.is_running = True
        logger.info("Scheduler started")
        # In production, would set up recurring tasks with APScheduler
        # For now, this is a placeholder

    async def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        logger.info("Scheduler stopped")

    async def manual_recompute(self, asset_id: Optional[int] = None):
        """Manually trigger recomputation"""
        ctx = JobContext()
        if asset_id:
            await recompute_metrics_for_asset(asset_id, ctx)
        else:
            await recompute_all_active_assets(ctx=ctx)


# Global scheduler instance
scheduler = Scheduler(enabled=False)  # Set via environment variable in main.py


async def scheduler_loop(interval_minutes: int, batch_size: int):
    """Background loop that periodically recomputes metrics and alerts"""
    # Run forever until cancelled
    while True:
        ctx = JobContext()
        try:
            await recompute_all_active_assets(limit=batch_size, ctx=ctx)
        except asyncio.CancelledError:
            # Exit gracefully on cancellation
            logger.info(f"[{ctx.job_id}] Scheduler loop cancelled")
            break
        except Exception as e:
            logger.error(f"[{ctx.job_id}] Scheduler loop error: {e}")
        # Sleep until next interval
        await asyncio.sleep(max(1, interval_minutes) * 60)


def create_scheduler_task(interval_minutes: int, batch_size: int) -> asyncio.Task:
    """Create an asyncio Task for the scheduler loop"""
    return asyncio.create_task(scheduler_loop(interval_minutes, batch_size))


def cancel_scheduler_task(task: asyncio.Task):
    """Cancel the scheduler task"""
    if task and not task.done():
        task.cancel()
