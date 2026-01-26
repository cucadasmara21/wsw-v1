"""
Consolidación única de conexiones a bases de datos con fallbacks para Replit
SQLAlchemy 2.x compatible con text() para queries raw
TIMESCALEDB:  optional, explicit ENABLE_TIMESCALE flag
"""
import logging
from contextlib import contextmanager
from typing import Optional, Generator, Dict, Any
from sqlalchemy import create_engine, text, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
# Redis and Neo4j are optional. Import if available, otherwise disable features gracefully.
try:
    import redis
except ImportError:
    redis = None
    logger = logging.getLogger(__name__)
    logger.info("ℹ️  Redis package not installed; Redis features will be disabled unless installed from requirements-optional.txt")

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None
    logger = logging.getLogger(__name__)
    logger.info("ℹ️  Neo4j package not installed; Neo4j features will be disabled unless installed from requirements-optional.txt")

from config import settings
from backend.db.dsn import get_sqlalchemy_url

logger = logging.getLogger(__name__)

# ==================== POSTGRESQL/SQLITE ====================

engine_kwargs = {}
if settings.USE_SQLITE:
    engine_kwargs = {"connect_args": {"check_same_thread": False}}
else:
    engine_kwargs = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size":  5,
        "max_overflow":  10
    }

# Ensure DSN normalization is the single source of truth.
engine = create_engine(get_sqlalchemy_url(default=settings.DATABASE_URL), **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
metadata = MetaData()

# ==================== TITAN V8 SCHEMA (POSTGRES) ====================


def ensure_v8_schema() -> None:
    """
    Idempotent Postgres-first bootstrap for TITAN V8 canonical objects.

    IMPORTANT:
    - Runs in isolated transaction scopes (engine.begin()) so failures never poison pooled connections.
    - Handles the case where a legacy *table* named public.assets already exists by renaming it
      to public.assets_legacy and then creating a compatibility VIEW public.assets backed by
      public.universe_assets.
    """
    if settings.USE_SQLITE:
        return

    # 0) If public.universe_assets is missing but public.assets exists, canonicalize by VIEW:
    #     public.universe_assets -> public.assets
    # This avoids split-brain naming across the codebase while preserving existing data.
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
            has_universe = bool(conn.execute(text("SELECT to_regclass('public.universe_assets') IS NOT NULL")).scalar())
            has_assets = bool(conn.execute(text("SELECT to_regclass('public.assets') IS NOT NULL")).scalar())
            if not has_universe and has_assets:
                conn.execute(text("CREATE OR REPLACE VIEW public.universe_assets AS SELECT * FROM public.assets;"))
                logger.info("✅ Created view public.universe_assets -> public.assets (canonical bridge)")
                return
    except Exception as e:
        logger.warning(f"⚠️ Could not canonicalize universe_assets via assets view: {type(e).__name__}: {e}")

    # 1) Canonical table + required columns (when no legacy assets table exists)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS public.universe_assets (
                      asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                      symbol text UNIQUE,
                      sector text,
                      morton_code bigint,
                      taxonomy32 integer,
                      meta32 integer,
                      x real,
                      y real,
                      z real,
                      fidelity_score real,
                      spin real,
                      vertex_buffer bytea,
                      governance_status text NOT NULL DEFAULT 'PROVISIONAL',
                      last_quantum_update timestamptz NOT NULL DEFAULT now()
                    );
                    """
                )
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_universe_assets_morton ON public.universe_assets(morton_code);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_universe_assets_sector ON public.universe_assets(sector);"))
            logger.info("✅ Ensured table public.universe_assets (canonical)")
    except Exception as e:
        logger.warning(f"⚠️ Could not ensure public.universe_assets: {type(e).__name__}: {e}")
        return

    # 3) Optional MV for V8 snapshots
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DO $$
                    BEGIN
                      IF to_regclass('public.universe_assets') IS NOT NULL THEN
                        IF to_regclass('public.universe_snapshot_v8') IS NULL THEN
                          CREATE MATERIALIZED VIEW public.universe_snapshot_v8 AS
                          SELECT morton_code, vertex_buffer
                          FROM public.universe_assets;
                          CREATE INDEX IF NOT EXISTS idx_universe_snapshot_v8_morton
                            ON public.universe_snapshot_v8(morton_code);
                        END IF;
                      END IF;
                    END $$;
                    """
                )
            )
    except Exception as e:
        logger.warning(f"⚠️ Could not ensure public.universe_snapshot_v8 MV: {type(e).__name__}: {e}")


def ensure_min_universe_seed(min_rows: int = 2000) -> int:
    """
    Keep the app usable even when the DB is empty:
    - Ensures canonical V8 schema exists
    - If public.universe_assets has 0 rows, inserts a deterministic synthetic universe (min_rows)
    Returns the resulting rowcount (best effort).
    """
    if settings.USE_SQLITE:
        return 0
    try:
        ensure_v8_schema()
    except Exception:
        # Best-effort only; don't crash startup
        return 0

    try:
        from services.synthetic_universe import seed_universe_assets_if_empty

        return int(seed_universe_assets_if_empty(engine, min_rows=int(min_rows)) or 0)
    except Exception:
        return 0


# ==================== REDIS (OPCIONAL) ====================

redis_client:  Optional["redis.Redis"] = None
if settings.ENABLE_REDIS:
    if redis is None:
        logger.warning("⚠️  Redis package not installed; Redis disabled. Install `requirements-optional.txt` to enable.")
    else:
        try:
            redis_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=False
            )
            redis_client.ping()
            logger.info("✅ Redis conectado exitosamente")
        except Exception as e:
            logger.warning(f"⚠️  Redis no disponible: {e}. Usando cache en memoria.")
            redis_client = None
else:
    logger.info("ℹ️  Redis deshabilitado por configuración")

# ==================== NEO4J (OPCIONAL) ====================

neo4j_driver: Optional[Any] = None
if settings.ENABLE_NEO4J:
    if GraphDatabase is None:
        logger.warning("⚠️  Neo4j package not installed; Neo4j disabled. Install `requirements-optional.txt` to enable.")
    else:
        try:
            neo4j_driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                connection_timeout=5
            )
            with neo4j_driver.session() as session:
                session.run("RETURN 1")
            logger.info("✅ Neo4j conectado exitosamente")
        except Exception as e:
            logger.warning(f"⚠️  Neo4j no disponible:  {e}. Operaciones deshabilitadas.")
            neo4j_driver = None
else:
    logger.info("ℹ️  Neo4j deshabilitado por configuración")

# ==================== FUNCIONES DE UTILIDAD ====================


def get_db() -> Generator[Session, None, None]: 
    """Dependency para obtener sesión de base de datos"""
    db = SessionLocal()
    try:
        yield db
    finally: 
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager para sesiones de base de datos"""
    db = SessionLocal()
    try:
        yield db
    finally: 
        db.close()


def test_connections() -> Dict[str, Any]:
    """Probar todas las conexiones sin lanzar excepciones"""
    status = {
        "postgres": False,
        "redis": False,
        "neo4j": False,
    }

    # Test PostgreSQL/SQLite
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            status["postgres"] = True
    except Exception as e:
        logger.error(f"❌ DB error: {e}")
        status["postgres_error"] = str(e)

    # Test Redis
    if redis_client:
        try: 
            redis_client.ping()
            status["redis"] = True
        except Exception as e: 
            logger.error(f"❌ Redis error: {e}")
            status["redis_error"] = str(e)
    else:
        status["redis"] = None

    # Test Neo4j
    if neo4j_driver: 
        try:
            with neo4j_driver.session() as session:
                session.run("RETURN 1")
            status["neo4j"] = True
        except Exception as e:
            logger.error(f"❌ Neo4j error: {e}")
            status["neo4j_error"] = str(e)
    else:
        status["neo4j"] = None

    return status


def init_database() -> bool:
    """
    Inicializar base de datos (crear tablas si no existen)
    TIMESCALEDB: try/except per tabla, no crash si falla
    """
    try: 
        # Crear todas las tablas
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tablas creadas/verificadas")

        # Postgres-first bootstrap for TITAN V8 canonical objects (idempotent).
        # Use isolated transactions to avoid poisoned pooled connections.
        ensure_v8_schema()

        # ==================== TIMESCALEDB ====================
        if settings.ENABLE_TIMESCALE and not settings.USE_SQLITE: 
            logger.info("🔧 Habilitando TimescaleDB...")

            # Crear extensión
            try:
                with engine.connect() as conn:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
                    conn.commit()
                logger.info("✅ Extensión TimescaleDB OK")
            except Exception as e: 
                logger.warning(f"⚠️  Extensión error: {e}")

            # Crear hypertable:  prices
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        SELECT create_hypertable(
                            'prices',
                            'time',
                            if_not_exists => TRUE
                        );
                    """))
                    conn.commit()
                logger.info("✅ Hypertable 'prices' OK")
            except Exception as e: 
                logger.warning(f"⚠️  prices error: {e}")

            # Crear hypertable: risk_metrics
            try:
                with engine.connect() as conn:
                    conn.execute(text("""
                        SELECT create_hypertable(
                            'risk_metrics',
                            'time',
                            if_not_exists => TRUE
                        );
                    """))
                    conn.commit()
                logger.info("✅ Hypertable 'risk_metrics' OK")
            except Exception as e:
                logger.warning(f"⚠️  risk_metrics error:  {e}")
        else:
            if settings.ENABLE_TIMESCALE: 
                logger.info("ℹ️  TimescaleDB disabled (SQLite detected)")
            else:
                logger.info("ℹ️  TimescaleDB disabled (ENABLE_TIMESCALE=false)")

        # Ensure risk_snapshots table exists (schema used by MVP risk vector)
        # IMPORTANT: this must be dialect-safe (SQLite vs PostgreSQL).
        try:
            with engine.connect() as conn:
                dialect = engine.dialect.name
                if dialect == "sqlite":
                    # SQLite-only DDL (AUTOINCREMENT + PRAGMA) must never run on Postgres.
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS risk_snapshots (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            ts TEXT NOT NULL,
                            asset_id TEXT,
                            price_risk REAL,
                            liq_risk REAL,
                            fund_risk REAL,
                            cp_risk REAL,
                            regime_risk REAL,
                            cri REAL,
                            model_version VARCHAR(32)
                        );
                    """))
                    cols = conn.execute(text("PRAGMA table_info(risk_snapshots)")).mappings().all()
                    existing = {c['name'] for c in cols}
                    if 'asset_name' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN asset_name TEXT"))
                    if 'group_name' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN group_name TEXT"))
                    if 'subgroup_name' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN subgroup_name TEXT"))
                    if 'category_name' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN category_name TEXT"))
                    if 'fundamental_risk' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN fundamental_risk REAL"))
                        if 'fund_risk' in existing:
                            conn.execute(text("UPDATE risk_snapshots SET fundamental_risk = fund_risk"))
                    if 'liquidity_risk' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN liquidity_risk REAL"))
                        if 'liq_risk' in existing:
                            conn.execute(text("UPDATE risk_snapshots SET liquidity_risk = liq_risk"))
                    if 'counterparty_risk' not in existing:
                        conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN counterparty_risk REAL"))
                        if 'cp_risk' in existing:
                            conn.execute(text("UPDATE risk_snapshots SET counterparty_risk = cp_risk"))
                else:
                    # Postgres-safe DDL.
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS risk_snapshots (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            ts TIMESTAMPTZ NOT NULL,
                            asset_id TEXT,
                            price_risk DOUBLE PRECISION,
                            liq_risk DOUBLE PRECISION,
                            fund_risk DOUBLE PRECISION,
                            cp_risk DOUBLE PRECISION,
                            regime_risk DOUBLE PRECISION,
                            cri DOUBLE PRECISION,
                            model_version VARCHAR(32),
                            asset_name TEXT,
                            group_name TEXT,
                            subgroup_name TEXT,
                            category_name TEXT,
                            fundamental_risk DOUBLE PRECISION,
                            liquidity_risk DOUBLE PRECISION,
                            counterparty_risk DOUBLE PRECISION
                        );
                    """))
                    # Columns are included above; keep idempotent ALTERs for older schemas.
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS asset_name TEXT;"))
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS group_name TEXT;"))
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS subgroup_name TEXT;"))
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS category_name TEXT;"))
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS fundamental_risk DOUBLE PRECISION;"))
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS liquidity_risk DOUBLE PRECISION;"))
                    conn.execute(text("ALTER TABLE risk_snapshots ADD COLUMN IF NOT EXISTS counterparty_risk DOUBLE PRECISION;"))

                # Ensure indexes (dialect-agnostic)
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_risk_snapshots_ts ON risk_snapshots(ts);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_risk_snapshots_asset_id ON risk_snapshots(asset_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_risk_snapshots_group_subcat ON risk_snapshots(group_name,subgroup_name,category_name);"))
                conn.commit()
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure risk_snapshots table (dialect-safe): {e}")

        # Ensure indicator_snapshots table has required columns/indexes (SQLite-safe)
        try:
            if settings.USE_SQLITE:
                with engine.connect() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS indicator_snapshots (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            symbol TEXT NOT NULL,
                            timeframe TEXT DEFAULT '1d',
                            ts TEXT NOT NULL,
                            sma_20 REAL,
                            rsi_14 REAL,
                            risk_v0 REAL,
                            explain_json TEXT,
                            snapshot_json TEXT,
                            created_at TEXT
                        );
                    """))
                    cols = conn.execute(text("PRAGMA table_info(indicator_snapshots)")).mappings().all()
                    existing = {c['name'] for c in cols}
                    if 'timeframe' not in existing:
                        conn.execute(text("ALTER TABLE indicator_snapshots ADD COLUMN timeframe TEXT DEFAULT '1d'"))
                    if 'snapshot_json' not in existing:
                        conn.execute(text("ALTER TABLE indicator_snapshots ADD COLUMN snapshot_json TEXT"))
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_indicator_snapshot_symbol_tf_ts ON indicator_snapshots(symbol,timeframe,ts);"))
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure indicator_snapshots table: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")
        return False

# database.py (añade esto si no existe)
def init_db():
    # Importante: registrar modelos antes de create_all
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
