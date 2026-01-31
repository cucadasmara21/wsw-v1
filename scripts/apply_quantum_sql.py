#!/usr/bin/env python3
"""
Apply Quantum Materialization SQL
Runs quantum_materialization.sql to create MV and triggers.
"""
import asyncio
import sys
from pathlib import Path

root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))

try:
    import asyncpg
except ImportError:
    print("ERROR: asyncpg required. Install: pip install asyncpg")
    sys.exit(1)

try:
    from config import settings
except ImportError as e:
    print(f"ERROR: Failed to import config: {e}")
    sys.exit(1)


async def main():
    dsn = settings.DATABASE_DSN_ASYNC or settings.normalize_async_dsn(settings.DATABASE_URL)
    
    if not dsn or dsn.startswith('sqlite'):
        print("ERROR: DATABASE_DSN_ASYNC must be a PostgreSQL connection string")
        sys.exit(1)
    
    sql_file = root_path / "backend" / "sql" / "quantum_materialization.sql"
    
    if not sql_file.exists():
        print(f"ERROR: SQL file not found: {sql_file}")
        sys.exit(1)
    
    print(f"Reading SQL from: {sql_file}")
    sql_content = sql_file.read_text()
    
    print("Connecting to database...")
    conn = await asyncpg.connect(dsn)
    
    try:
        print("Executing SQL...")
        await conn.execute(sql_content)
        print("✓ SQL applied successfully")
        
        # Verify MV exists
        mv_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1 FROM pg_matviews
                WHERE matviewname = 'quantum_assets_mv'
            )
        """)
        
        if mv_exists:
            print("✓ Materialized view 'quantum_assets_mv' created")
        else:
            print("⚠ Materialized view not found (check SQL for errors)")
        
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
