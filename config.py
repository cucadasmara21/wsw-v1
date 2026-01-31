"""
Configuración centralizada con fallbacks para Replit
Compatible con pydantic-settings 2.x
ENABLE_TIMESCALE como variable explícita (no auto-detectar)
"""
import os
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationError
import logging

logger = logging.getLogger(__name__)

# Centralized DSN normalization (sync SQLAlchemy + asyncpg).
from backend.db.dsn import get_sqlalchemy_url, normalize_asyncpg_dsn, normalize_sqlalchemy_url

def _resolve_env_path() -> Path:
    """
    Resolve .env path from repo root (cwd-proof).
    Supports both repo-root config.py and backend/config.py layouts.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parent / ".env",          # config.py at repo root
        here.parents[1] / ".env",      # config.py inside backend/ (one level deeper)
    ]
    for p in candidates:
        if p.exists():
            return p
    # Default to first candidate (repo-root location) for warning context
    return candidates[0]


_env_path = _resolve_env_path()
if not _env_path.exists():
    logger.warning(f".env not found at {_env_path} (cwd-proof lookup); DATABASE_URL must be set for Route A.")


def redact_database_url(url: str) -> str:
    """Redact password from database URL for safe logging."""
    if not url:
        return url
    try:
        if "@" in url:
            parts = url.split("@")
            if len(parts) == 2:
                auth_part = parts[0]
                rest = parts[1]
                if "://" in auth_part:
                    scheme_part = auth_part.split("://")[0] + "://"
                    creds = auth_part.split("://")[1]
                    if ":" in creds:
                        user = creds.split(":")[0]
                        return f"{scheme_part}{user}:***@{rest}"
                    return f"{scheme_part}***@{rest}"
        return url
    except Exception:
        return (url[:50] + "...") if len(url) > 50 else url


def parse_db_scheme(url: str) -> str:
    """Extract database scheme from URL."""
    if not url:
        return "unknown"
    url_lower = url.lower()
    if url_lower.startswith("postgresql") or url_lower.startswith("postgres"):
        return "postgresql"
    if url_lower.startswith("sqlite"):
        return "sqlite"
    return "unknown"


class Settings(BaseSettings):
    """Configuración de la aplicación con fallbacks"""

    model_config = SettingsConfigDict(
        env_file=str(_env_path) if _env_path.exists() else None,
        case_sensitive=False,
        extra="ignore",
    )

    # ==================== ENTORNO ====================
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")

    # ==================== API ====================
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="PORT")  # Replit usa $PORT

    # ==================== BASE DE DATOS ====================
    DATABASE_URL: str = Field(
        # Route A: Postgres-only, must be explicitly provided.
        default="",
        env=("DATABASE_URL", "POSTGRES_DSN"),
    )
    
    # Async DSN for asyncpg (normalized from DATABASE_URL)
    DATABASE_DSN_ASYNC: Optional[str] = Field(default=None, env="DATABASE_DSN_ASYNC")
    
    # ==================== REDIS (OPCIONAL) ====================
    REDIS_URL: Optional[str] = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    
    # ==================== UNIVERSE CONFIG ====================
    UNIVERSE_TARGET_COUNT: int = Field(default=10000, env="UNIVERSE_TARGET_COUNT")
    ENABLE_PARTITIONS: bool = Field(default=False, env="ENABLE_PARTITIONS")
    # P-04: VoidPool slot recycling. When True: Death/Birth wired; fail-fast if pool fails.
    ENABLE_VOIDPOOL: bool = Field(default=True, env="ENABLE_VOIDPOOL")
    # Provenance: when True, add ingestion_run_id/source/observed_at/row_digest to Route A tables.
    ENABLE_PROVENANCE: bool = Field(default=False, env="ENABLE_PROVENANCE")

    # ==================== NEO4J (OPCIONAL) ====================
    NEO4J_URI: Optional[str] = Field(default=None, env="NEO4J_URI")
    NEO4J_USER: Optional[str] = Field(default="neo4j", env="NEO4J_USER")
    NEO4J_PASSWORD: Optional[str] = Field(default=None, env="NEO4J_PASSWORD")

    # ==================== TIMESCALEDB (EXPLÍCITO) ====================
    ENABLE_TIMESCALE: bool = Field(default=False, env="ENABLE_TIMESCALE")

    # ==================== SEGURIDAD ====================
    SECRET_KEY: str = Field(
        default="dev-secret-key-change-in-production",
        env="SECRET_KEY"
    )
    ALGORITHM: str = Field(default="HS256", env="ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    # ==================== CORS ====================
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://localhost:8000",
        env="CORS_ORIGINS"
    )

    # ==================== TRUSTED HOSTS ====================
    TRUSTED_HOSTS: str = Field(default="", env="TRUSTED_HOSTS")

    # ==================== ADMIN (para seed) ====================
    ADMIN_EMAIL: str = Field(default="admin@wsw.local", env="ADMIN_EMAIL")
    ADMIN_PASSWORD: str = Field(default="admin123456", env="ADMIN_PASSWORD")

    # ==================== SCHEDULER (OPCIONAL) ====================
    ENABLE_SCHEDULER: bool = Field(default=False, env="ENABLE_SCHEDULER")
    SCHEDULER_INTERVAL_MINUTES: int = Field(default=5, env="SCHEDULER_INTERVAL_MINUTES")
    SCHEDULER_BATCH_SIZE: int = Field(default=50, env="SCHEDULER_BATCH_SIZE")

    # ==================== INGESTION PROVIDERS ====================
    FRED_API_KEY: Optional[str] = Field(default=None, env="FRED_API_KEY")
    POLYGON_API_KEY: Optional[str] = Field(default=None, env="POLYGON_API_KEY")
    DISABLE_POLYGON: bool = Field(default=True, env="DISABLE_POLYGON")
    EODHD_API_KEY: Optional[str] = Field(default=None, env="EODHD_API_KEY")
    COINGECKO_API_KEY: Optional[str] = Field(default=None, env="COINGECKO_API_KEY")
    INGEST_CONCURRENCY: int = Field(default=8, env="INGEST_CONCURRENCY")
    INGEST_LIMIT_ASSETS: int = Field(default=2000, env="INGEST_LIMIT_ASSETS")
    INGEST_PROVIDER_PRIMARY: str = Field(default="polygon", env="INGEST_PROVIDER_PRIMARY")
    INGEST_PROVIDER_BACKUP: str = Field(default="eodhd", env="INGEST_PROVIDER_BACKUP")

    # ==================== BANDERAS DERIVADAS ====================
    ENABLE_REDIS: bool = False
    ENABLE_NEO4J: bool = False
    # Route A: keep flag for older modules, always False (SQLite forbidden).
    USE_SQLITE: bool = False

    @field_validator('ENABLE_REDIS', mode='before')
    @classmethod
    def validate_enable_redis(cls, v, info):
        """Habilitar Redis si REDIS_URL está configurado"""
        return bool(info.data.get('REDIS_URL'))

    @field_validator('ENABLE_NEO4J', mode='before')
    @classmethod
    def validate_enable_neo4j(cls, v, info):
        """Habilitar Neo4j si todas las credenciales están presentes"""
        return all([
            info.data.get('NEO4J_URI'),
            info.data.get('NEO4J_USER'),
            info.data.get('NEO4J_PASSWORD')
        ])

    @field_validator('DATABASE_DSN_ASYNC', mode='before')
    @classmethod
    def validate_database_dsn_async(cls, v, info):
        """Normalize async DSN from DATABASE_URL if not explicitly set"""
        if v:
            return normalize_asyncpg_dsn(str(v))
        db_url = info.data.get('DATABASE_URL', '')
        if db_url:
            # Route A: Postgres-only
            return normalize_asyncpg_dsn(str(db_url))
        return None

    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def validate_database_url(cls, v, info):
        """
        Normalize DATABASE_URL for SQLAlchemy:
        - Accept postgresql:// and upgrade to postgresql+psycopg2:// for Windows reliability.
        - Preserve sqlite:// if explicitly set (legacy-only).
        """
        if v is None:
            v = ""
        s = v.strip() if isinstance(v, str) else str(v)
        if not s:
            raise ValueError("DATABASE_URL is required (Route A: PostgreSQL-only).")

        sl = s.lower()
        if sl.startswith("sqlite"):
            raise ValueError("SQLite is not allowed (Route A: PostgreSQL-only).")

        out = normalize_sqlalchemy_url(s)
        if parse_db_scheme(out) != "postgresql":
            raise ValueError("DATABASE_URL must be PostgreSQL (postgresql:// or postgresql+psycopg2://).")
        return out
    
    @staticmethod
    def normalize_async_dsn(dsn: str) -> str:
        """Convert SQLAlchemy DSN to asyncpg DSN"""
        return normalize_asyncpg_dsn(dsn)

    @field_validator('DISABLE_POLYGON', mode='before')
    @classmethod
    def validate_disable_polygon(cls, v):
        """Parse DISABLE_POLYGON env var. Default True (disabled by default)."""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            # Empty string or "0"/"false"/"no" = False (enable Polygon)
            # "1"/"true"/"yes" = True (disable Polygon)
            v_lower = v.strip().lower()
            if v_lower in ('', '0', 'false', 'no'):
                return False
            return v_lower in ('1', 'true', 'yes')
        # Default: True (disabled)
        return True if v is None else bool(v)

    @property
    def cors_origins_list(self) -> List[str]:
        """Convierte CORS_ORIGINS a lista"""
        if not self.CORS_ORIGINS:
            return []
        return [origin.strip() for origin in self.CORS_ORIGINS.split(',')]

    @property
    def trusted_hosts_list(self) -> List[str]:
        """Convierte TRUSTED_HOSTS a lista"""
        if not self.TRUSTED_HOSTS:
            return []
        return [host.strip() for host in self.TRUSTED_HOSTS.split(',')]

# Instancia global de configuración (Route A: fail-fast).
# If DATABASE_URL is missing/invalid (e.g., sqlite), the backend MUST NOT start.
try:
    settings = Settings()
except ValidationError as e:
    raise RuntimeError(
        "Invalid configuration (Route A: PostgreSQL-only). "
        "Set DATABASE_URL to a PostgreSQL DSN (postgresql:// or postgresql+psycopg2://)."
    ) from e
except Exception as e:
    raise RuntimeError("Failed to load configuration (Route A: PostgreSQL-only).") from e

# Log de configuración
db_scheme = parse_db_scheme(settings.DATABASE_URL)
v8_ready = db_scheme == "postgresql"
logger.info(f"Env: {settings.ENVIRONMENT}")
logger.info(f"DB: {redact_database_url(settings.DATABASE_URL)}")
logger.info(f"DB Scheme: {db_scheme}")
logger.info(f"V8 Ready: {v8_ready} (requires PostgreSQL)")
logger.info(f"Redis enabled: {bool(settings.ENABLE_REDIS)}")
logger.info(f"Neo4j enabled: {bool(settings.ENABLE_NEO4J)}")
logger.info(f"TimescaleDB enabled: {bool(settings.ENABLE_TIMESCALE and not settings.USE_SQLITE)}")
logger.info(f"Scheduler enabled: {bool(settings.ENABLE_SCHEDULER)} (interval={settings.SCHEDULER_INTERVAL_MINUTES}m, batch={settings.SCHEDULER_BATCH_SIZE})")

# Log provider API keys (presence only, no secrets)
polygon_loaded = bool(settings.POLYGON_API_KEY)
polygon_disabled = bool(settings.DISABLE_POLYGON)
fred_loaded = bool(settings.FRED_API_KEY)
logger.info(f"Providers: POLYGON_API_KEY={polygon_loaded} DISABLE_POLYGON={polygon_disabled} FRED_API_KEY={fred_loaded}")
if settings.DEBUG and not polygon_loaded and not fred_loaded:
    logger.warning("⚠️  No provider API keys configured. Asset detail quotes will fail. Set POLYGON_API_KEY or FRED_API_KEY in .env")