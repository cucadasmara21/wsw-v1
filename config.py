"""
Configuración centralizada con fallbacks para Replit
Compatible con pydantic-settings 2.x
ENABLE_TIMESCALE como variable explícita (no auto-detectar)
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Configuración de la aplicación con fallbacks"""

    # ==================== ENTORNO ====================
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")

    # ==================== API ====================
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="PORT")  # Replit usa $PORT

    # ==================== BASE DE DATOS ====================
    DATABASE_URL: str = Field(
        default="sqlite:///./wsw.db",
        env="DATABASE_URL"
    )

    # ==================== REDIS (OPCIONAL) ====================
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")

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
        default="http://localhost:3000,http://localhost:8000",
        env="CORS_ORIGINS"
    )

    # ==================== TRUSTED HOSTS ====================
    TRUSTED_HOSTS: str = Field(default="", env="TRUSTED_HOSTS")

    # ==================== ADMIN (para seed) ====================
    ADMIN_EMAIL: str = Field(default="admin@wsw.local", env="ADMIN_EMAIL")
    ADMIN_PASSWORD: str = Field(default="admin123456", env="ADMIN_PASSWORD")

    # ==================== BANDERAS DERIVADAS ====================
    ENABLE_REDIS: bool = False
    ENABLE_NEO4J: bool = False
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

    @field_validator('USE_SQLITE', mode='before')
    @classmethod
    def validate_use_sqlite(cls, v, info):
        """Detectar si se usa SQLite"""
        db_url = info.data.get('DATABASE_URL', '')
        return 'sqlite' in db_url. lower()

    @property
    def cors_origins_list(self) -> List[str]:
        """Convierte CORS_ORIGINS a lista"""
        if not self.CORS_ORIGINS:
            return []
        return [origin.strip() for origin in self.CORS_ORIGINS. split(',')]

    @property
    def trusted_hosts_list(self) -> List[str]:
        """Convierte TRUSTED_HOSTS a lista"""
        if not self. TRUSTED_HOSTS:
            return []
        return [host. strip() for host in self.TRUSTED_HOSTS.split(',')]

    class Config:
        env_file = ".env"
        case_sensitive = False


# Instancia global de configuración
settings = Settings()

# Log de configuración
logger.info(f"🔧 Entorno: {settings.ENVIRONMENT}")
logger.info(f"🗄️  DB:  {settings.DATABASE_URL[: 50]}...")
logger.info(f"🔴 Redis: {'✅' if settings.ENABLE_REDIS else '❌'}")
logger.info(f"🔵 Neo4j: {'✅' if settings.ENABLE_NEO4J else '❌'}")
logger.info(f"⏱️  TimescaleDB: {'✅' if settings.ENABLE_TIMESCALE and not settings.USE_SQLITE else '❌'}")