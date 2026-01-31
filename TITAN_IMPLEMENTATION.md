# Titan High-Fidelity Rendering Implementation

## Repo Digest

**Backend Entrypoint:** `main.py` (FastAPI app)
- Routers mounted under `/api/*` prefix
- OpenAPI docs: `/api/docs`, `/api/openapi.json`
- Health endpoint: `/api/health`

**Auth Dependency:** `api/auth.py`
- `get_current_user()` with DEBUG bypass for GET requests
- Returns mock sovereign admin user when `settings.DEBUG=True` and `request.method == "GET"`

**Universe Endpoints:** `api/universe.py`
- `/api/universe/tree` - JSON tree structure
- `/api/universe/points` - JSON point cloud (legacy)
- `/api/universe/points.meta` - Titan metadata (NEW)
- `/api/universe/points.bin` - Titan binary stream (NEW, 12-byte stride)

**Telemetry:** `api/v1/routers/telemetry_ws.py`
- WebSocket: `/ws/v1/telemetry`
- Heartbeat every 1s with `points_count` field

**Frontend:**
- API client: `frontend/src/lib/api.ts` (API_BASE="/api")
- Vite proxy: `frontend/vite.config.ts` (proxies /api -> 127.0.0.1:8000)
- Canvas: `frontend/src/components/UniverseCanvas.tsx` (legacy JSON)
- Titan Canvas: `frontend/src/components/TitanCanvas.tsx` (NEW, binary stream)

**Bitmask Encoder:** `engines/bitmask_encoder.py`
- Canonical layout: domain(0-2) | outlier(3) | risk16(4-19) | reserved(20-31)

**Stress Seed:** `scripts/stress_seed.py`
- Generates 100k clustered assets with Titan taxonomy32 + canonical mask
- Supports SQLite and PostgreSQL (asyncpg)

## Run Commands

### Backend
```bash
cd C:\Users\alber\Documents\wsw-v1
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Seed Database (100k assets)
```bash
cd C:\Users\alber\Documents\wsw-v1
python scripts/stress_seed.py --n 100000 --reset
```

### Frontend
```bash
cd C:\Users\alber\Documents\wsw-v1\frontend
npm run dev
```

## Smoke Test Checklist

### Backend Endpoints
- [ ] `GET http://127.0.0.1:8000/api/health` → 200 OK
- [ ] `GET http://127.0.0.1:8000/api/assets?limit=5` → 200 OK, JSON array
- [ ] `GET http://127.0.0.1:8000/api/universe/tree` → 200 OK, tree structure
- [ ] `GET http://127.0.0.1:8000/api/universe/points.meta` → 200 OK, `{"count": N, "stride_bytes": 12, ...}`
- [ ] `GET http://127.0.0.1:8000/api/universe/points.bin` → 200 OK, `Content-Length == count * 12`

### Frontend
- [ ] Navigate to `http://127.0.0.1:5173/universe`
- [ ] Click "View Canvas" → Titan mode renders clustered galaxies
- [ ] Toggle "Titan Mode" / "Legacy Mode" → Both render correctly
- [ ] Network tab shows requests to `/api/universe/points.bin` (no `/api/api`)

### Database
- [ ] After seeding: `SELECT COUNT(*) FROM assets WHERE is_active = 1` → ~100000
- [ ] Columns exist: `titan_taxonomy32`, `canonical_mask_u32`, `x`, `y`
- [ ] Indexes exist: `ix_assets_titan_taxonomy32`, `ix_assets_canonical_mask`

### Visual Validation
- [ ] 100k points render at stable frame time (no main-thread stalls)
- [ ] Visible clustered "galaxies" (not uniform noise)
- [ ] Color varies by domain (6 monoliths)
- [ ] Luminosity varies by risk
- [ ] Outliers pulse (5% of points)
- [ ] Point size varies by cluster (deterministic, no flicker)

## Titan Binary Format

**Stride:** 12 bytes per point (little-endian)

```
Offset 0:  x_u16      (UNSIGNED_SHORT, 2 bytes)
Offset 2:  y_u16      (UNSIGNED_SHORT, 2 bytes)
Offset 4:  titan_u32  (UNSIGNED_INT, 4 bytes)
Offset 8:  canonical_u32 (UNSIGNED_INT, 4 bytes)
```

**Titan Taxonomy32 Layout (8-8-8-8):**
- B3 (bits 31-24): `(monolith<<5) | cluster` (prefix index)
- B2 (bits 23-16): subcluster
- B1 (bits 15-8): category/temporal
- B0 (bits 7-0): variant/hash leaf

**Canonical Mask Layout:**
- Bits 0-2: domain (0-5)
- Bit 3: outlier (0 or 1)
- Bits 4-19: risk16 (0-65535)
- Bits 20-31: reserved

## Performance Targets

- 100k points render at stable frame time (no stalls)
- Buffer updates incremental (chunked), never full realloc
- Deterministic LOD decimation in shader
- Zero-copy binary upload to GPU
