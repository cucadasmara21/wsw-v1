# Instrucciones para agentes Copilot

Propósito: proporcionar a un agente de IA la información mínima y específica para ser productivo inmediatamente en este repositorio.

## Visión general (big picture)
- Aplicación backend FastAPI (entrypoint: `main.py`). Diseñada para ser "Replit-ready" (sin Docker por defecto) y con inicialización perezosa de servicios opcionales.
- Persistencia: SQLAlchemy 2.x (sin migraciones automáticas). `init_database()` crea tablas con `Base.metadata.create_all()` en `database.py`.
- Componentes principales:
  - `config.py` → pydantic-settings (2.x) y derivaciones: `ENABLE_REDIS`, `ENABLE_NEO4J`, `USE_SQLITE`.
  - `database.py` → `engine`, `SessionLocal`, `redis_client`, `neo4j_driver`, `init_database()`, `test_connections()`.
  - `models.py` → modelos: `Asset`, `Price` (clave compuesta `time`+`asset_id`), `RiskMetric`, `User`, `Alert`.
  - `ingest.py` → script de ingesta (yfinance + pandas) que inserta `Price` y crea activos según sea necesario.
  - `init_db.py` → script simple que llama a `init_database()`.
  - `main.py` → registros, ciclo de vida (lifespan), middlewares y registro de routers (`api.*`).

Para detalles extensos sobre arquitectura, ontología, algoritmos cuantitativos y roadmap, ver `WHITEPAPER.md` en la raíz del repositorio.

## Convenciones y patrones de este proyecto
- Estructura de routers: `api` debe exportar `router` por módulo (ej.: `auth.router`, `assets.router`) y `main.py` los registra con prefijos `/api/...`.
- Capa de servicios: `services` contiene la lógica de negocio (ej.: `data_service.py`, `cache_service.py`). Sigue usar una clase de servicio que reciba `db` (Session) o use `cache_service` global.
- Dependencias DB: usar `get_db()` (generator) o `SessionLocal()` con `try/finally`/context manager para cerrar sesiones.
- Fallbacks externos: Redis y Neo4j son opcionales — el código está escrito para no fallar si no están presentes. Habilítalos mediante variables de entorno (ver abajo).
- TimescaleDB: se activa explícitamente con `ENABLE_TIMESCALE=true` y **no** debe usarse con SQLite (`USE_SQLITE` se deriva automáticamente).
- Manejo de errores: los scripts y `init_database()` intentan operaciones opcionales (crear extension/hypertables) en try/except; conservar lógica para evitar crash en entornos sin servicios.

**Notas de instalación:**
- `requirements.txt` contiene la pila mínima (FastAPI, SQLAlchemy, JWT auth).
- Para análisis/ingesta (pandas, yfinance, numpy, matplotlib) usa `requirements-analytics.txt`.
- Para integraciones opcionales (Redis, Neo4j) usa `requirements-optional.txt`.
- `database.py` y `ingest.py` ahora toleran que `redis`, `neo4j`, `pandas` o `yfinance` no estén instalados — revisa los logs para habilitarlos.

## Comandos básicos / Flujo de desarrollo
- Instalar dependencias: `pip install -r requirements.txt`
- Configurar variables de entorno: `cp .env.example .env` y editar si procede (revisar `DATABASE_URL`, `REDIS_URL`, `NEO4J_URI`, `ENABLE_TIMESCALE`).
- Inicializar DB: `python init_db.py` (crea tablas y, si aplica, intenta crear hypertables para TimescaleDB).
- Ejecutar servidor en dev: `uvicorn main:app --host 0.0.0.0 --port 8000` (en Replit se usa `$PORT`).
- Ingesta de demo: `python ingest.py` (descarga datos con yfinance y los inserta en `prices`).
- Health check: `curl http://localhost:8000/health` — también útil: `/api/status` y `/api/config`.

## Variables de entorno relevantes
- `DATABASE_URL` (por defecto `sqlite:///./wsw.db`)
- `ENABLE_TIMESCALE` (true/false) — requiere PostgreSQL
- `REDIS_URL` → si presente activa `ENABLE_REDIS`
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` → si presentes activan Neo4j
- `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` (seed admin)

## Pautas específicas para un agente de IA (qué hacer/evitar)
- Cuando añadas endpoints, sigue la convención de crear `api/<name>.py` que exporte un `APIRouter` y registrar en `main.py` con `prefix="/api/<name>"` y tag correspondiente.
- Para acceso a BD dentro de endpoints, inyectar `db: Session = Depends(get_db)` o usar `get_db_session()` en scripts para asegurar cierre correcto.
- Mantener el manejo opcional de Redis/Neo4j: no asumir que están presentes; usa las señales (`settings.ENABLE_REDIS`, `settings.ENABLE_NEO4J`) o `redis_client`/`neo4j_driver` y cae en fallbacks.
- No introducir migraciones automáticamente: hoy el repo usa `Base.metadata.create_all` (no hay `alembic`); si añades cambios DDL complejos, considera agregar migraciones y documentación.
- Preservar el esquema unificado de `prices` (id compuesto `time+asset_id`): muchas consultas y la creación de hypertable dependen de ello.

## Ejemplos concretos (cortar y pegar)
- Registrar router en `main.py`:

```py
app.include_router(assets.router, prefix="/api/assets", tags=["assets"])
```

- Llamada para inicializar DB en `main.py` (ya presente en lifespan):

```py
success = init_database()
```

- Test de conexiones (útil al añadir integración externa):

```py
from database import test_connections
print(test_connections())
```

## Notas y limitaciones detectadas
- El `README.md` hace referencia a `python_services/` como carpeta; en este repo los módulos están en la raíz (ej.: `main.py`, `config.py`). Ten cuidado con rutas relativas al aplicar cambios.
- No se encontraron tests automatizados ni flujo CI. Tampoco hay migraciones (`alembic`) en el repo.
- Existe referencia a `tools/seed_admin.py` en el README; no se encontró ese archivo — puede faltar o estar en otro branch.

---

Si quieres, puedo:
1) Añadir tests básicos para `/health` y `/api/config` y un simple test de `init_db()`.
2) Crear una checklist de PR para cambios de DB (agregar migraciones, revisar Timescale).

¿Hay alguna sección que prefieras que amplíe o algún patrón interno que me pierda y deba documentar?