# 🏦 WallStreetWar - Sistema de Riesgo Sistémico Financiero

**MVP para Replit y Codespaces** - Backend FastAPI + Frontend React/TypeScript con configuración unificada. 

---

## Quick Start (Windows PowerShell)

### Prerequisites
- Python 3.12+ with virtual environment
- Node.js 18+
- PostgreSQL running (Docker or local)

### One command (starts Postgres + backend + frontend)
```powershell
# From repo root
.\scripts\dev.ps1
```

This script:
- Runs `docker compose up -d` (starts `wsw-postgres`)
- Waits for Postgres healthcheck
- Forces `DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/wsw_db` for the backend process
- Starts backend on `127.0.0.1:8000` (reload)
- Starts frontend on `127.0.0.1:5173` (Vite proxy to backend)

### Verification
```powershell
# Backend health
curl.exe -i http://localhost:8000/health

# V8 health (must show postgresql scheme and v8_ready=true)
curl.exe -i http://localhost:8000/api/universe/v8/health

# V8 snapshot (should return 200/204, not 503)
curl.exe -i "http://localhost:8000/api/universe/v8/snapshot?format=vertex28&compression=zstd"
```

If you want to run services manually (PowerShell):
```powershell
docker compose -f .\docker-compose.yml up -d
$env:DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
# Separate terminal:
cd .\frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

---

## 🚀 Quickstart (Un Comando)

### Windows (PowerShell)

```powershell
# Desde la raíz del repositorio
.\scripts\dev.ps1
```

Esto hará:
- ✅ Verificar Python y Node.js
- ✅ Crear `.env` si no existe
- ✅ Crear virtualenv e instalar dependencias
- ✅ Inicializar base de datos
- ✅ Iniciar backend en http://localhost:8000
- ✅ Iniciar frontend en http://localhost:5173

**Verificar:**
```powershell
# Salud del backend
curl http://localhost:8000/health

# Abrir frontend en el navegador
start http://localhost:5173
```

### Linux / macOS / Codespaces

```bash
# Desde la raíz del repositorio
./scripts/dev.sh
```

Esto hará:
- ✅ Verificar Python y Node.js
- ✅ Crear `.env` si no existe
- ✅ Crear virtualenv e instalar dependencias
- ✅ Inicializar base de datos
- ✅ Iniciar backend en http://localhost:8000
- ✅ Iniciar frontend en http://localhost:5173

**Verificar:**
```bash
# Salud del backend
curl http://localhost:8000/health

# Abrir frontend en el navegador (o usa la vista Ports en Codespaces)
```

---

## ✅ Verificación del Sistema

Antes de arrancar, puedes verificar que todo esté configurado correctamente:

### Windows
```powershell
.\scripts\check.ps1
```

### Linux / macOS / Codespaces
```bash
./scripts/check.sh
```

Esto comprueba:
- Python y Node.js instalados
- Virtualenv y dependencias instaladas
- Base de datos inicializada
- Archivo `.env` presente
- Puertos 8000 y 5173 disponibles

---

## 🔌 Endpoints Principales

Una vez iniciado el backend:

### Health Check (sin autenticación)
```bash
curl http://localhost:8000/health
```

Respuesta esperada:
```json
{
  "status": "healthy",
  "timestamp": "2026-01-11T...",
  "services": {
    "database": "healthy",
    "cache": "unavailable",
    "neo4j": "unavailable"
  }
}
```

### API Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Otros endpoints
- `/api/assets` - Gestión de activos
- `/api/risk/overview` - Visión general de riesgo
- `/api/scenarios/run` - Ejecutar escenarios
- `/api/auth/token` - Autenticación JWT
- `/api/metrics/{asset_id}/metrics` - Último snapshot de métricas
- `/api/alerts` - Listado y gestión de alertas

---

## 🔧 Troubleshooting

### Puerto 8000 o 5173 ocupado

**Síntoma:** Error al iniciar: "Port 8000 is busy"

**Windows:**
```powershell
# Ver qué proceso usa el puerto
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess

# Matar el proceso
Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process
```

**Linux/macOS:**
```bash
# Ver qué proceso usa el puerto
lsof -i:8000

# Matar el proceso
lsof -ti:8000 | xargs kill -9
```

### Archivo .env faltante

**Síntoma:** Advertencia "⚠️ .env file not found"

**Solución:**
```bash
# Linux/macOS
cp .env.example .env

# Windows
Copy-Item .env.example .env
```

Luego edita `.env` según sea necesario. Por defecto usa SQLite y no requiere configuración adicional.

### Python o Node.js no encontrado

**Síntoma:** "❌ Python not found" o "❌ Node.js not found"

**Solución:**
- **Python:** Instala Python 3.10+ desde [python.org](https://python.org)
- **Node.js:** Instala Node.js 18+ desde [nodejs.org](https://nodejs.org)

### Virtualenv no activado

**Síntoma:** "ModuleNotFoundError: No module named 'fastapi'"

**Solución:**
```bash
# Linux/macOS/Codespaces
source .venv/bin/activate

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Windows CMD
.\.venv\Scripts\activate.bat
```

### Base de datos no inicializada

**Síntoma:** Errores relacionados con tablas faltantes

**Solución:**
```bash
# Asegúrate de que el virtualenv esté activado primero
python init_db.py
```

### CORS errors en el navegador

**Síntoma:** "Access to fetch at 'http://localhost:8000/api/...' from origin 'http://localhost:5173' has been blocked by CORS policy"

**Solución:**
1. Verifica que `.env` incluya ambos puertos:
   ```env
   CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000
   ```
2. Reinicia el backend después de cambiar `.env`

### Frontend muestra página en blanco

**Síntoma:** `http://localhost:5173` carga pero no muestra contenido

**Posibles causas:**
1. **Backend no está corriendo** - Verifica http://localhost:8000/health
2. **Error en el proxy de Vite** - Revisa la consola del navegador y los logs de terminal
3. **Dependencias frontend faltantes** - Ejecuta `cd frontend && npm ci`

### Problemas en Codespaces

**Puertos no accesibles:**
1. Ve a la vista "Ports" en VS Code
2. Asegúrate de que los puertos 8000 y 5173 estén reenviados
3. Cambia la visibilidad a "Public" si es necesario

**Backend/Frontend no inician:**
- Usa `--host 0.0.0.0` en lugar de `127.0.0.1`:
  ```bash
  # Backend
  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
  
  # Frontend
  npm run dev
  ```

---

## 📁 Estructura del Proyecto
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

```
/ (raíz del repositorio)
├── main.py                   ← Entrypoint FastAPI
├── config.py                 ← Configuración (pydantic-settings)
├── database.py               ← Conexiones SQL+Redis+Neo4j
├── models.py                 ← ORM SQLAlchemy
├── schemas.py                ← Validación Pydantic
├── init_db.py                ← Script de inicialización de BD
├── ingest.py                 ← Ingesta de datos (yfinance)
├── requirements.txt          ← Dependencias mínimas
├── requirements-analytics.txt← Dependencias opcionales (pandas, yfinance)
├── requirements-optional.txt ← Redis, Neo4j
├── .env.example              ← Plantilla de configuración
├── api/
│   ├── assets.py             ← GET /api/assets
│   ├── risk.py               ← GET /api/risk/overview
│   ├── scenarios.py          ← POST /api/scenarios/run
│   └── auth.py               ← POST /api/auth/token
├── services/
│   ├── data_service.py       ← Lógica de negocio
│   └── cache_service.py      ← Cache con fallback
├── tools/
│   └── seed_admin.py         ← Crear usuario admin
├── scripts/
│   ├── dev.sh                ← Script de desarrollo (Linux/macOS)
│   ├── dev.ps1               ← Script de desarrollo (Windows)
│   ├── check.sh              ← Verificación del sistema (Linux/macOS)
│   └── check.ps1             ← Verificación del sistema (Windows)
└── frontend/
    ├── src/
    │   ├── main.tsx          ← Entry point
    │   ├── App.tsx           ← Componente principal
    │   ├── components/       ← Componentes React
    │   ├── pages/            ← Páginas de la app
    │   └── api/              ← Cliente API TypeScript
    ├── vite.config.ts        ← Configuración Vite (con proxy)
    └── package.json
```

---

## ✨ Características

- **SQLite por defecto** ✅ Funciona sin configuración adicional
- **PostgreSQL + TimescaleDB** ✅ Opcional vía `ENABLE_TIMESCALE`
- **Redis opcional** ✅ Fallback automático a memoria
- **Neo4j opcional** ✅ No falla si no está disponible
- **Frontend React/TypeScript** ✅ Con proxy Vite integrado
- **Scripts cross-platform** ✅ Un comando en Windows, Linux o Codespaces
- **SQLAlchemy 2.x** ✅ ORM moderno
- **FastAPI** ✅ API moderna con documentación automática
- **Whitepaper técnico** 📘 Ver `WHITEPAPER.md` para arquitectura detallada

---

## 🔑 Variables de Entorno

El archivo `.env.example` contiene todas las configuraciones necesarias. Los scripts de desarrollo lo copian automáticamente a `.env` si no existe.

### Configuración por defecto (SQLite)

```env
ENVIRONMENT=development
DEBUG=true
DATABASE_URL=sqlite:///./wsw.db
ENABLE_TIMESCALE=false
SECRET_KEY=your-secret-key-change-in-production
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://localhost:8000
ENABLE_SCHEDULER=false
SCHEDULER_INTERVAL_MINUTES=5
SCHEDULER_BATCH_SIZE=50
```

### Para PostgreSQL + TimescaleDB

```env
DATABASE_URL=postgresql://user:password@host:5432/wsw
ENABLE_TIMESCALE=true
```

### Para habilitar Redis (opcional)

```env
REDIS_URL=redis://localhost:6379/0
```

### Para habilitar Neo4j (opcional)

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

### Para habilitar el Scheduler (opcional)

```env
ENABLE_SCHEDULER=true
SCHEDULER_INTERVAL_MINUTES=5
SCHEDULER_BATCH_SIZE=50
```

Con esto, el backend ejecutará cada N minutos la recomputación de métricas y generación de alertas para un subconjunto de activos.
```

## 🧪 Testing Manual

Después de iniciar con `.\scripts\run-backend.ps1` y `.\scripts\run-frontend.ps1`:

```bash
# 1. Health check
curl http://localhost:8000/health

# 2. Listar activos (vacío inicialmente)
curl http://localhost:8000/api/assets

# 3. Ver configuración
curl http://localhost:8000/api/config

# 5. Ver métricas y alertas (requiere auth en producción)
# GET snapshot de métricas (id de activo de ejemplo: 1)
curl http://localhost:8000/api/metrics/1/metrics

# GET alertas
curl http://localhost:8000/api/alerts

# 4. Ver documentación interactiva
# Abrir en navegador: http://localhost:8000/docs
```

## TITAN V8 Quantum Seeding

Para poblar `universe_assets` con datos sintéticos:

### Prerrequisitos
- PostgreSQL en Docker (o local) - **REQUIRED for V8**
- Variables de entorno configuradas (`.env` en repo root)
- Verificar V8 readiness:
  ```powershell
  # Check V8 health (must show database_url_scheme: "postgresql")
  curl.exe -i http://localhost:8000/api/universe/v8/health
  
  # Test V8 snapshot (should return 200/204, not 503)
  curl.exe -i "http://localhost:8000/api/universe/v8/snapshot?format=vertex28&compression=zstd"
  ```

### Windows (PowerShell) - Runbook Completo

```powershell
# 1. Set DSN asyncpg (ambos para compatibilidad)
$env:DATABASE_URL="postgresql://postgres:postgres@localhost:5432/wsw_db"
$env:DATABASE_DSN_ASYNC="postgresql://postgres:postgres@localhost:5432/wsw_db"

# 2. Bootstrap legacy (crea source_assets + prices)
python scripts/bootstrap_legacy.py --n 10000 --days 30 --reset

# 3. Aplicar SQL materialization (auto-heal)
.\scripts\apply_quantum_sql.ps1

# 4. Seed V8 (concurrencia 4, batch 2000, con verificación)
python backend/scripts/seed_universe_v8.py --target 10000 --concurrency 4 --batch 2000 --verify
```

### Linux / macOS

```bash
# 1. Set DSN asyncpg
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/wsw_db"
export DATABASE_DSN_ASYNC="postgresql://postgres:postgres@localhost:5432/wsw_db"

# 2. Bootstrap legacy
python scripts/bootstrap_legacy.py --n 10000 --days 30 --reset

# 3. Aplicar SQL materialization
python scripts/db_apply_sql.py quantum_materialization.sql

# 4. Seed V8
python backend/scripts/seed_universe_v8.py --target 10000 --concurrency 4 --batch 2000 --verify
```

### Validación

```bash
# Verificar counts
docker exec -it wsw-postgres psql -U postgres -d wsw_db -c "SELECT COUNT(*) FROM source_assets;"
docker exec -it wsw-postgres psql -U postgres -d wsw_db -c "SELECT COUNT(*) FROM universe_assets;"
docker exec -it wsw-postgres psql -U postgres -d wsw_db -c "SELECT MIN(octet_length(vertex_buffer)), MAX(octet_length(vertex_buffer)) FROM universe_assets;"
```

---

## 📚 Documentación Adicional

- **Whitepaper técnico:** Ver [WHITEPAPER.md](WHITEPAPER.md) para arquitectura detallada, ontología, modelos cuantitativos y roadmap
- **Guía de desarrollo:** Ver [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) para flujos de trabajo avanzados
- **Guía de pre-commit:** Ver [docs/PRECOMMIT.md](docs/PRECOMMIT.md) para hooks y validaciones

---

## 🤝 Contribuir

1. Fork el repositorio
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

---

## 📝 Licencia

Este proyecto es un MVP académico/demostrativo para análisis de riesgo sistémico financiero.

---

## 🆘 Soporte

Si tienes problemas:

1. **Primero:** Ejecuta el script de verificación
   - Windows: `.\scripts\check.ps1`
   - Linux/macOS: `./scripts/check.sh`

2. **Revisa la sección de Troubleshooting** arriba

3. **Consulta logs:**
   - Backend: Revisa la salida de la terminal donde corre uvicorn
   - Frontend: Revisa la consola del navegador (F12)

4. **Abre un issue** en GitHub con:
   - Sistema operativo
   - Versiones de Python y Node.js
   - Salida del comando que falla
   - Logs relevantes
