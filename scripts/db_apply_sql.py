#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import asyncpg

def dsn_async() -> str:
    dsn = os.getenv("DATABASE_DSN_ASYNC") or os.getenv("DATABASE_URL") or ""
    dsn = dsn.strip()
    if dsn.startswith("postgresql+psycopg://"):
        dsn = "postgresql://" + dsn[len("postgresql+psycopg://"):]
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://"):]
    if not dsn.startswith("postgresql://"):
        raise SystemExit("ERROR: DATABASE_URL / DATABASE_DSN_ASYNC must be postgresql://... (asyncpg-compatible)")
    return dsn

async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql_path", type=str)
    args = ap.parse_args()

    sql = open(args.sql_path, "r", encoding="utf-8").read()
    dsn = dsn_async()

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
        print(f"[OK] Applied SQL: {args.sql_path}")
    finally:
        await conn.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
