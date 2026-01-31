from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from fastapi import HTTPException

from config import settings
from services.ingest_service import ingest_run

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["ingestion"])


@router.post("/run")
async def run_ingestion(
    limit: int = Query(2000, ge=1, le=10000),
    concurrency: Optional[int] = Query(None),
):
    if not settings.DEBUG:
        raise HTTPException(status_code=403, detail="Ingestion requires DEBUG mode")

    concurrency = concurrency or settings.INGEST_CONCURRENCY

    try:
        result = await ingest_run(limit_assets=limit, concurrency=concurrency)
        return result
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
