"""
Punto de entrada principal FastAPI - Replit Ready
NOTA: No ejecuta seed automáticamente. 
Usar: python tools/seed_admin.py
"""
import logging
import uuid
import subprocess
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import uvicorn
from sqlalchemy import text

from config import settings
from database import engine, get_db, init_database, test_connections, neo4j_driver
from models import Base
from api import assets, risk, scenarios, auth, market, universe
from services.cache_service import cache_service

# Build info
def _get_git_sha() -> str:
    try:
        out = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL)
        return out.decode().strip()
    except Exception:
        return "unknown"

BUILD_INFO = {
    "git_sha": _get_git_sha(),
    "build_time": datetime.utcnow().isoformat()
}

# Logger - Structured logging with request tracking
class RequestIDFilter(logging.Filter):
    """Add request_id to all log records"""
    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = 'startup'
        return True

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s'
)
logger = logging.getLogger(__name__)
logger.addFilter(RequestIDFilter())
# Also add filter to root logger
logging.getLogger().addFilter(RequestIDFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestión del ciclo de vida"""
    logger.info("🚀 Iniciando WallStreetWar API en Replit...")
    logger.info(f"📍 Entorno: {settings.ENVIRONMENT}")
    logger.info(f"🔧 Debug: {settings.DEBUG}")
    logger.info(f"🔌 DB:  {settings.DATABASE_URL[: 40]}...")

    try:
        success = init_database()
        if success:
            logger.info("✅ Base de datos inicializada")
        else:
            logger.warning("⚠️  BD no completamente inicializada")
    except Exception as e:
        logger.error(f"❌ Error DB: {e}")

    try:
        connections = test_connections()
        logger.info(f"📊 Conexiones:")
        logger.info(f"   - PostgreSQL/SQLite: {'✅' if connections.get('postgres') else '❌'}")
        logger.info(f"   - Redis: {'✅' if connections.get('redis') else '⊘' if connections.get('redis') is None else '❌'}")
        logger.info(f"   - Neo4j: {'✅' if connections.get('neo4j') else '⊘' if connections.get('neo4j') is None else '❌'}")
    except Exception as e:
        logger.error(f"⚠️  Error conexiones: {e}")

    try:
        cache_service.initialize()
        logger.info("✅ Cache inicializado")
    except Exception as e:
        logger.warning(f"⚠️  Error cache: {e}")

    yield

    logger.info("🛑 Apagando WallStreetWar API...")
    try:
        cache_service.close()
    except:
        pass


from fastapi.responses import JSONResponse
from sqlalchemy.exc import InvalidRequestError, NoForeignKeysError

app = FastAPI(
    title="WallStreetWar API",
    description="Sistema de riesgo sistémico financiero (MVP Replit)",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)


@app.exception_handler(InvalidRequestError)
async def sqlalchemy_invalid_request_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Schema configuration issue: missing or ambiguous foreign key relationships (Category.assets). Summary endpoints may be affected.", "error": str(exc)})


@app.exception_handler(NoForeignKeysError)
async def sqlalchemy_nofk_handler(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Schema configuration issue: missing foreign key links for relationships.", "error": str(exc)})


# Global exception handler for consistency
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTPException with request_id"""
    request_id = request.headers.get("X-Request-Id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.status_code,
                "message": exc.detail,
                "request_id": request_id
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions gracefully"""
    request_id = request.headers.get("X-Request-Id", "unknown")
    logger.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": 500,
                "message": "Internal Server Error",
                "request_id": request_id
            }
        }
    )


# Request ID middleware with logging context
@app.middleware("http")
async def add_request_id_header(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    logger.info(f"[{request_id}] {request.method} {request.url.path}")
    try:
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        logger.info(f"[{request_id}] Response: {response.status_code}")
    except Exception as e:
        logger.exception(f"[{request_id}] Unhandled error: {e}")
        raise
    return response


# Middlewares
origins = settings.cors_origins_list if settings.cors_origins_list else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

if settings.trusted_hosts_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts_list)

# Routers
app.include_router(auth.router, prefix="/api/auth")
app.include_router(assets.router, prefix="/api/assets")
app.include_router(universe.router, prefix="/api/universe")
app.include_router(risk.router, prefix="/api/risk")
app.include_router(scenarios.router, prefix="/api/scenarios")
app.include_router(market.router, prefix="/api/market")


@app.get("/")
async def root():
    return {
        "message": "WallStreetWar Systemic Risk Engine",
        "version": "1.0.0",
        "status": "operational",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "endpoints": {
            "health": "/health",
            "docs": "/docs" if settings.DEBUG else None,
            "assets": "/api/assets",
            "risk": "/api/risk",
            "scenarios": "/api/scenarios",
            "auth": "/api/auth"
        }
    }


@app.get("/health")
async def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e: 
        logger.error(f"❌ Health check DB failed: {e}")
        db_status = "unhealthy"

    redis_status = "unavailable"
    try:
        if hasattr(cache_service, 'is_connected') and cache_service.is_connected():
            redis_status = "healthy"
    except: 
        redis_status = "unavailable"

    neo4j_status = "unavailable"
    try: 
        if neo4j_driver: 
            with neo4j_driver.session() as session:
                session.run("RETURN 1")
            neo4j_status = "healthy"
    except:
        neo4j_status = "unavailable"

    overall_status = "healthy" if db_status == "healthy" else "degraded"

    return {
        "status":  overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "services": {
            "database": db_status,
            "cache": redis_status,
            "neo4j": neo4j_status
        },
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG
    }


@app.get('/version', tags=["System"])
async def version():
    """Return build info including git sha, build time, and environment"""
    return {
        "app": "WallStreetWar",
        "version": "1.0.0",
        "git_sha": BUILD_INFO.get("git_sha"),
        "build_time": BUILD_INFO.get("build_time"),
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG
    }

@app.get("/api/status")
async def system_status():
    from services.data_service import DataService
    from database import SessionLocal

    try:
        db = SessionLocal()
        data_service = DataService(db)
        return {
            "system": "WallStreetWar",
            "version": "1.0.0",
            "environment": settings.ENVIRONMENT,
            "timestamp": datetime.utcnow().isoformat(),
            "statistics": {
                "assets_count": data_service.count_assets(),
                "prices_count": data_service.count_prices(),
                "risk_metrics_calculated": 0,
                "alerts_active": 0
            },
            "database_url": settings.DATABASE_URL[: 50] + "..."
        }
    except Exception as e:
        logger.error(f"❌ /api/status error: {e}")
        return {
            "system": "WallStreetWar",
            "version": "1.0.0",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


@app.get("/api/config")
async def get_config():
    return {
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "database":  {
            "type": "sqlite" if settings.USE_SQLITE else "postgresql",
            "timescale_enabled": settings.ENABLE_TIMESCALE
        },
        "cache": {
            "redis_enabled": settings.ENABLE_REDIS
        },
        "neo4j": {
            "enabled": settings.ENABLE_NEO4J
        },
        "api": {
            "host": settings.API_HOST,
            "port": settings.API_PORT,
            "cors_origins": settings.cors_origins_list,
        },
        "timestamp": datetime.utcnow().isoformat()
    }


if __name__ == "__main__": 
    logger.info(f"🚀 Iniciando en {settings.API_HOST}:{settings.API_PORT}")
    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
