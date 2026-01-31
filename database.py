"""
Consolidación única de conexiones a bases de datos con fallbacks para Replit
SQLAlchemy 2.x compatible con text() para queries raw
TIMESCALEDB:  optional, explicit ENABLE_TIMESCALE flag

Route A (TITAN V8) invariants:
- PostgreSQL only (fail-fast if unreachable; see `config.py` + `main.py` lifespan gate).
- Vertex28 binary contract only (stride=28 bytes per point, stored in `public.universe_assets.vertex_buffer`).
- Taxonomy/meta fields are BIGINT in SQL; when packing to uint32, mask with & 0xFFFFFFFF.

Validation (DoD snippets):
- psql: SELECT to_regclass('public._stg_universe_assets'), to_regclass('public.universe_assets'), to_regclass('public.universe_snapshot_v8');
- psql: SELECT data_type FROM information_schema.columns WHERE table_schema='public' AND table_name='_stg_universe_assets' AND column_name IN ('taxonomy32','meta32');
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

# ==================== POSTGRESQL (Route A only) ====================

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 5,
    "max_overflow": 10,
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
    - Route A: PostgreSQL-only + Vertex28.
    - Route A `public.assets` is a stable *VIEW* sourced from `public.source_assets` (canonical ingestion layer),
      not the legacy ORM table `assets`.

    Validation (DoD snippets):
    - psql: SELECT COUNT(*) FROM public.source_assets; SELECT COUNT(*) FROM public.universe_assets;
    - psql: SELECT MIN(octet_length(vertex_buffer)), MAX(octet_length(vertex_buffer)) FROM public.universe_assets;
    """
    # 0) Extensions required by schema defaults (gen_random_uuid()).
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

    # 1) Canonical table + required columns
    with engine.begin() as conn:
        # Optional upstream source layer. Route A seeders may synthesize this table
        # so downstream checks and other tooling remain deterministic.
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.source_assets (
                  asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  id uuid,
                  symbol text UNIQUE NOT NULL,
                  sector text,
                  x real,
                  y real,
                  z real,
                  meta32 bigint,
                  titan_taxonomy32 bigint
                );
                """
            )
        )
        # Ensure Route A join keys exist (DoD expects source_assets.id).
        conn.execute(text("ALTER TABLE public.source_assets ADD COLUMN IF NOT EXISTS id uuid;"))
        conn.execute(text("UPDATE public.source_assets SET id = gen_random_uuid() WHERE id IS NULL;"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_source_assets_id ON public.source_assets(id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_source_assets_symbol ON public.source_assets(symbol);"))

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public.universe_assets (
                  asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                  source_id uuid,
                  symbol text UNIQUE,
                  sector text,
                  morton_code bigint,
                  taxonomy32 bigint NOT NULL DEFAULT 0,
                  meta32 bigint NOT NULL DEFAULT 0,
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
        # Route A join key (DoD expects universe_assets.source_id).
        conn.execute(text("ALTER TABLE public.universe_assets ADD COLUMN IF NOT EXISTS source_id uuid;"))

        # If an older schema created taxonomy32/meta32 as integer, upgrade to bigint.
        # Drop dependent MV first to avoid ALTER TYPE failures.
        conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS public.universe_snapshot_v8 CASCADE;"))
        conn.execute(
            text(
                """
                DO $$
                DECLARE
                  t_tax text;
                  t_meta text;
                BEGIN
                  SELECT data_type INTO t_tax
                  FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='universe_assets' AND column_name='taxonomy32';

                  IF t_tax IS NOT NULL AND t_tax <> 'bigint' THEN
                    EXECUTE 'ALTER TABLE public.universe_assets ALTER COLUMN taxonomy32 TYPE bigint USING taxonomy32::bigint';
                  END IF;

                  SELECT data_type INTO t_meta
                  FROM information_schema.columns
                  WHERE table_schema='public' AND table_name='universe_assets' AND column_name='meta32';

                  IF t_meta IS NOT NULL AND t_meta <> 'bigint' THEN
                    EXECUTE 'ALTER TABLE public.universe_assets ALTER COLUMN meta32 TYPE bigint USING meta32::bigint';
                  END IF;
                END $$;
                """
            )
        )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_universe_assets_morton ON public.universe_assets(morton_code);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_universe_assets_sector ON public.universe_assets(sector);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_universe_assets_source_id ON public.universe_assets(source_id);"))

        # Route A staging table (required by runbooks + deterministic seeder).
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS public._stg_universe_assets (
                  asset_id uuid,
                  source_id uuid,
                  symbol text,
                  sector text,
                  morton_code bigint,
                  taxonomy32 bigint NOT NULL,
                  meta32 bigint NOT NULL,
                  x real,
                  y real,
                  z real,
                  risk real,
                  shock real,
                  vertex_buffer bytea
                );
                """
            )
        )
        # Ensure columns exist even if table pre-existed (Route A)
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS asset_id uuid;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS source_id uuid;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS symbol text;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS sector text;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS morton_code bigint;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS taxonomy32 bigint;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS meta32 bigint;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS x real;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS y real;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS z real;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS risk real;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS shock real;"))
        conn.execute(text("ALTER TABLE public._stg_universe_assets ADD COLUMN IF NOT EXISTS vertex_buffer bytea;"))
        # Enforce UNIQUE(symbol) at the index level (idempotent repair from older non-unique indexes).
        conn.execute(text("DROP INDEX IF EXISTS public.ix__stg_universe_assets_symbol;"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux__stg_universe_assets_symbol ON public._stg_universe_assets(symbol);"))

        # Stable Route A assets view (ingestion truth).
        # NOTE: this is a VIEW, not the legacy ORM table `assets`.
        conn.execute(
            text(
                """
                CREATE OR REPLACE VIEW public.assets AS
                SELECT
                  sa.asset_id,
                  sa.id AS source_id,
                  sa.symbol,
                  COALESCE(NULLIF(btrim(sa.symbol), ''), 'UNKNOWN') AS name,
                  sa.sector,
                  NULL::text AS industry,
                  COALESCE(sa.titan_taxonomy32, 0)::bigint AS taxonomy32,
                  COALESCE(sa.meta32, 0)::bigint AS meta32
                FROM public.source_assets sa;
                """
            )
        )

        logger.info("✅ Ensured Route A canonical schema objects (source_assets/universe_assets/_stg_universe_assets/assets view)")

    # 2) Best-effort repair: keep source_assets and universe_assets joinable by symbol.
    try:
        with engine.begin() as conn:
            # Backfill source_assets from universe_assets if needed.
            conn.execute(
                text(
                    """
                    INSERT INTO public.source_assets (symbol, sector, x, y, z, meta32, titan_taxonomy32)
                    SELECT DISTINCT
                      ua.symbol,
                      ua.sector,
                      ua.x, ua.y, ua.z,
                      ua.meta32,
                      ua.taxonomy32
                    FROM public.universe_assets ua
                    WHERE ua.symbol IS NOT NULL AND ua.symbol <> ''
                    ON CONFLICT (symbol) DO UPDATE SET
                      sector=EXCLUDED.sector,
                      x=EXCLUDED.x, y=EXCLUDED.y, z=EXCLUDED.z,
                      meta32=EXCLUDED.meta32,
                      titan_taxonomy32=EXCLUDED.titan_taxonomy32;
                    """
                )
            )
            conn.execute(text("UPDATE public.source_assets SET id = gen_random_uuid() WHERE id IS NULL;"))
            conn.execute(
                text(
                    """
                    UPDATE public.universe_assets ua
                    SET source_id = sa.id
                    FROM public.source_assets sa
                    WHERE ua.source_id IS NULL AND ua.symbol = sa.symbol;
                    """
                )
            )
    except Exception as e:
        logger.warning("⚠️ Route A join repair skipped: %s: %s", type(e).__name__, e)

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
        # Route A: avoid ORM auto-DDL (can conflict with Route A views and cause index duplication issues).
        # Canonical DDL is managed explicitly in ensure_v8_schema().

        # Postgres-first bootstrap for TITAN V8 canonical objects (idempotent).
        # Use isolated transactions to avoid poisoned pooled connections.
        ensure_v8_schema()

        # ==================== TIMESCALEDB ====================
        if settings.ENABLE_TIMESCALE:
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
            logger.info("ℹ️  TimescaleDB disabled (ENABLE_TIMESCALE=false)")

        # Ensure risk_snapshots table exists (PostgreSQL only in Route A)
        try:
            with engine.begin() as conn:
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
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure risk_snapshots table: {e}")

        # Ensure indicator_snapshots table (PostgreSQL only in Route A)
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS indicator_snapshots (
                          id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                          symbol TEXT NOT NULL,
                          timeframe TEXT NOT NULL DEFAULT '1d',
                          ts TIMESTAMPTZ NOT NULL,
                          sma_20 DOUBLE PRECISION,
                          rsi_14 DOUBLE PRECISION,
                          risk_v0 DOUBLE PRECISION,
                          explain_json TEXT,
                          snapshot_json TEXT,
                          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                        );
                        """
                    )
                )
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ix_indicator_snapshot_symbol_tf_ts ON indicator_snapshots(symbol,timeframe,ts);"
                    )
                )
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure indicator_snapshots table: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")
        raise

# database.py (añade esto si no existe)
def init_db():
    # Importante: registrar modelos antes de create_all
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
