"""
Script de inicialización de base de datos
SQLAlchemy 2.x compatible
"""
import logging
from database import engine, Base, init_database
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    logger.info("🚀 Inicializando base de datos...")
    success = init_database()
    if success:
        logger.info("✅ BD inicializada correctamente")
    else:
        logger.error("❌ Error inicializando BD")
        return False
    return True


if __name__ == "__main__":
    main()