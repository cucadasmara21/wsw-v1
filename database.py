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

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
metadata = MetaData()

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
        # Use a safe CREATE TABLE IF NOT EXISTS so this is idempotent across runs
        try:
            with engine.connect() as conn:
                # Create table if missing
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
                # Ensure desired columns exist; add missing ones via ALTER TABLE
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

                # Ensure indexes
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_risk_snapshots_ts ON risk_snapshots(ts);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_risk_snapshots_asset_id ON risk_snapshots(asset_id);"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_risk_snapshots_group_subcat ON risk_snapshots(group_name,subgroup_name,category_name);"))
        except Exception as e:
            logger.warning(f"⚠️ Could not ensure risk_snapshots table: {e}")

        return True
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")
        return False

# database.py (añade esto si no existe)
def init_db():
    # Importante: registrar modelos antes de create_all
    import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
