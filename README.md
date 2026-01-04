# 🏦 WallStreetWar - Sistema de Riesgo Sistémico Financiero

**MVP para Replit** - Backend FastAPI sin Docker, lazy init para servicios opcionales. 

## 🚀 Arranque Rápido

### En Replit (Automático)

El archivo `.replit` ejecuta automáticamente:

```bash
cd python_services && uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Local (Manual)

```bash
# 1. Instalar dependencias
pip install -r python_services/requirements.txt

# 2. Inicializar base de datos
cd python_services
python init_db.py

# 3. (OPCIONAL) Crear usuario admin
python tools/seed_admin.py

# 4. Arrancar servidor
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 🔌 Endpoints Principales

### 1️⃣ Health Check (Sin credenciales)

```bash
curl -X GET http://localhost:8000/health
```

**Respuesta esperada:**
```json
{
  "status": "healthy",
  "timestamp": "2026-01-04T14:30:45.123456",
  "services": {
    "database": "healthy",
    "cache": "unavailable",
    "neo4j": "unavailable"
  },
  "environment": "development",
  "debug": true
}
```

### 2️⃣ Obtener Activos

```bash
curl -X GET "http://localhost:8000/api/assets? limit=10"
```

**Respuesta esperada (array vacío inicialmente):**
```json
[]
```

### 3️⃣ Visión de Riesgo

```bash
curl -X GET "http://localhost:8000/api/risk/overview?limit=10"
```

---

## 🔑 Variables de Entorno

Copiar `.env.example` a `.env` en `python_services/`:

```bash
cp python_services/.env.example python_services/.env
```

### Configuración por defecto (SQLite):

```env
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=sqlite:///./wsw.db
ENABLE_TIMESCALE=false
ADMIN_EMAIL=admin@wsw.local
ADMIN_PASSWORD=admin123456
```

### Para PostgreSQL + TimescaleDB:

```env
DATABASE_URL=postgresql://user:password@host:5432/wsw
ENABLE_TIMESCALE=true
```

---

## 📁 Estructura

```
python_services/
├── main.py                   ← Entrypoint FastAPI
├── config.py                 ← Configuración (pydantic-settings)
├── database. py               ← Conexiones SQL+Redis+Neo4j
├── models.py                 ← ORM SQLAlchemy (prices, assets, risk_metrics, users, alerts)
├── schemas.py                ← Pydantic (validación)
├── init_db.py                ← Inicializar BD
├── ingest.py                 ← Ingesta yfinance
├── api/
│   ├── __init__.py
│   ├── assets.py             ← GET /api/assets
│   ├── risk.py               ← GET /api/risk/overview
│   ├── scenarios.py          ← POST /api/scenarios/run
│   └── auth.py               ← POST /api/auth/token
├── services/
│   ├── __init__.py
│   ├── data_service.py       ← CRUD activos/precios/métricas
│   └── cache_service.py      ← Cache Redis+Memory fallback
├── tools/
│   ├── __init__.py
│   └── seed_admin.py         ← Crear admin (manual)
├── requirements.txt
└── . env. example
```

---

## ✨ Características

- **SQLite por defecto** ✅ Funciona en Replit sin setup
- **PostgreSQL + TimescaleDB** ✅ Optional via ENABLE_TIMESCALE
- **Redis opcional** ✅ Fallback automático a memoria
- **Neo4j opcional** ✅ No crashea si no está disponible
- **Schema unificado** ✅ prices(time, asset_id, ...)
- **SQLAlchemy 2.x** ✅ text() para queries raw
- **Admin seed manual** ✅ python tools/seed_admin.py

---

## 🧪 Testing

Después de arrancar, prueba los 3 endpoints:

```bash
# 1. Health
curl http://localhost:8000/health

# 2. Assets (vacío inicialmente)