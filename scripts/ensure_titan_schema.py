"""
Idempotent schema migration for Titan columns.

Ensures:
- assets table has x, y, meta32, titan_taxonomy32
- metrics_snapshot table exists
"""
from __future__ import annotations

import logging
from typing import Set

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


def _get_sqlite_columns(conn) -> Set[str]:
    rows = conn.exec_driver_sql("PRAGMA table_info(assets)").mappings().all()
    return {row["name"] for row in rows}


def ensure_schema(engine: Engine) -> None:
    """
    Idempotent migration for SQLite/Postgres via raw SQL.
    Must never raise on "already exists" conditions.
    """
    try:
        with engine.begin() as conn:
            dialect_name = conn.dialect.name.lower()
            is_sqlite = dialect_name.startswith("sqlite")

            # --- assets columns ---
            if is_sqlite:
                cols = _get_sqlite_columns(conn)

                if "x" not in cols:
                    try:
                        conn.exec_driver_sql("ALTER TABLE assets ADD COLUMN x REAL")
                    except Exception as e:
                        logger.warning(f"ensure_schema: add x failed (sqlite): {e}")

                if "y" not in cols:
                    try:
                        conn.exec_driver_sql("ALTER TABLE assets ADD COLUMN y REAL")
                    except Exception as e:
                        logger.warning(f"ensure_schema: add y failed (sqlite): {e}")

                if "meta32" not in cols:
                    try:
                        conn.exec_driver_sql(
                            "ALTER TABLE assets ADD COLUMN meta32 INTEGER DEFAULT 0"
                        )
                    except Exception as e:
                        logger.warning(f"ensure_schema: add meta32 failed (sqlite): {e}")

                if "titan_taxonomy32" not in cols:
                    try:
                        conn.exec_driver_sql(
                            "ALTER TABLE assets ADD COLUMN titan_taxonomy32 INTEGER DEFAULT 0"
                        )
                    except Exception as e:
                        logger.warning(
                            f"ensure_schema: add titan_taxonomy32 failed (sqlite): {e}"
                        )
            else:
                # Postgres / others: ADD COLUMN IF NOT EXISTS
                try:
                    conn.execute(text("ALTER TABLE assets ADD COLUMN IF NOT EXISTS x REAL"))
                except Exception as e:
                    logger.warning(f"ensure_schema: add x failed: {e}")
                try:
                    conn.execute(text("ALTER TABLE assets ADD COLUMN IF NOT EXISTS y REAL"))
                except Exception as e:
                    logger.warning(f"ensure_schema: add y failed: {e}")
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE assets "
                            "ADD COLUMN IF NOT EXISTS meta32 INTEGER DEFAULT 0"
                        )
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema: add meta32 failed: {e}")
                try:
                    conn.execute(
                        text(
                            "ALTER TABLE assets "
                            "ADD COLUMN IF NOT EXISTS titan_taxonomy32 INTEGER DEFAULT 0"
                        )
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema: add titan_taxonomy32 failed: {e}")

            # --- metrics_snapshot table ---
            try:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS metrics_snapshot (
                            id INTEGER PRIMARY KEY,
                            asset_id INTEGER NOT NULL,
                            ts TEXT NOT NULL,
                            meta32 INTEGER NOT NULL DEFAULT 0,
                            risk REAL,
                            shock REAL,
                            trend SMALLINT,
                            vitality SMALLINT,
                            macro SMALLINT
                        )
                        """
                    )
                )
            except Exception as e:
                logger.warning(f"ensure_schema: create metrics_snapshot failed: {e}")

        logger.info("ensure_schema: completed")
    except Exception as e:
        logger.error(f"ensure_schema: fatal error (non-blocking): {e}")
