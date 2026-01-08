# 🏦 WallStreetWar - Sistema de Riesgo Sistémico Financiero

**MVP para Replit** - Backend FastAPI sin Docker, lazy init para servicios opcionales. 

## 🚀 Arranque Rápido

### En Replit (Automático)

El archivo `.replit` ejecuta automáticamente:

```bash
cd python_services && uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Local (Manual)

#### Linux / macOS

```bash
# 1. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias mínimas (backend only)
pip install -r requirements.txt

# (Opcional) instalar dependencias de analytics e integraciones
# - Analytics (pandas, yfinance, numpy, matplotlib):
#   pip install -r requirements-analytics.txt
# - Integraciones opcionales (Redis, Neo4j):
#   pip install -r requirements-optional.txt

# 3. Inicializar base de datos
python init_db.py

# 4. Arrancar servidor
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

> Nota sobre Windows: el archivo `requirements.txt` contiene solo las dependencias mínimas del backend (sin extras de `uvicorn` como `uvloop`) para asegurar compatibilidad con Windows/CPython 3.12 sin compilar extensiones. Si necesitas rendimiento adicional en Linux, instala manualmente extras: `pip install 'uvicorn[standard]'`.
```

#### Windows (PowerShell / CMD) — Recomendado: Python 3.12

```powershell
# 1. Crear entorno virtual con Python 3.12
py -3.12 -m venv .venv
# 2. Activar entorno (PowerShell)
.\.venv\Scripts\Activate.ps1
# (o CMD)
.\.venv\Scripts\activate.bat

# 3. Actualizar pip
.\.venv\Scripts\python -m pip install -U pip setuptools wheel

# 4. Instalar dependencias (backend only)
.\.venv\Scripts\python -m pip install -r requirements.txt
# (Opcional) analytics/integrations
# .\.venv\Scripts\python -m pip install -r requirements-analytics.txt
# .\.venv\Scripts\python -m pip install -r requirements-optional.txt

# 5. Inicializar base de datos
.\.venv\Scripts\python init_db.py

# 6. Arrancar servidor
.\.venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

#### Codespaces / DevContainer

- Asegúrate de que el devcontainer use Python 3.12 (o selecciona la versión en la paleta).
- En la terminal integrada del Codespace (Linux container):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python init_db.py
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- Habilita/expón el puerto `8000` y `5173` (frontend) desde la vista Ports en Codespaces para que sean accesibles externamente.

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
- **Whitepaper técnico** 📘 Ver `WHITEPAPER.md` para la arquitectura detallada, ontología, modelos cuantitativos y roadmap
## Frontend (dev)

A minimal React + TypeScript frontend is available in `/frontend` (Vite). It uses a dev proxy so calls to `/api` and `/health` are forwarded to the backend at `http://localhost:8000`.

## Scripts de desarrollo (rápido)

- Linux / Codespaces (bash):

```bash
# Ejecutar desde la raíz del repositorio
./scripts/dev.sh
# Esto crea .venv, instala requirements.txt, ejecuta python init_db.py y arranca uvicorn en :8000 (con reload)
```

- Windows (PowerShell):

```powershell
# Ejecutar desde la raíz del repositorio
./scripts/dev.ps1
# Intenta usar `py -3.12` para crear el venv, instala requirements y arranca uvicorn en :8000 (con reload)
```

> Nota: El frontend del devserver usa por defecto el puerto `5173` y el backend `8000`; en Codespaces asegúrate de exponer ambos puertos.


Run locally:

```bash
# 1. Start backend (in one terminal)
source .venv/bin/activate
python init_db.py
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 2. Start frontend (in another terminal)
cd frontend
npm install
npm run dev
```

In Codespaces ensure ports `8000` (backend) and `5173` (frontend) are forwarded / visible.

---

## 🧪 Testing

Después de arrancar, prueba los 3 endpoints:

```bash
# 1. Health
curl http://localhost:8000/health

# 2. Assets (vacío inicialmente)