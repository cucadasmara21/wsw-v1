# PowerShell-Safe Validation Commands

## Backend Integrity Checks
```powershell
python -c "import scripts.ensure_titan_schema; print('OK ensure_titan_schema')"
python -c "import api.universe; print('OK api.universe')"
```

## Seed Galaxy
```powershell
python scripts/seed_galaxy.py
```

## Verify Endpoints
```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/universe/points.meta
```

```powershell
$r = Invoke-WebRequest http://127.0.0.1:8000/api/universe/points.bin?limit=10
$r.StatusCode
$r.Content.Length
```

## Start Backend
```powershell
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Start Frontend
```powershell
cd frontend
npm run dev
```

## Browser Verification
Open: http://127.0.0.1:5173/universe

Expected:
- /api/universe/points.meta shows count 10000 after seeding
- /api/universe/points.bin returns count*12 bytes with 200 OK
- Universe Titan page shows visible point cloud immediately (min 4px points) with cyan/magenta/white trend colors and zombie fading
