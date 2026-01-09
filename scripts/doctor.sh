#!/usr/bin/env bash
set -euo pipefail

echo "=== WallStreetWar Doctor ==="

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo
echo "[1/6] Repo"
git status -sb || true

echo
echo "[2/7] Versions & environment"
python --version || true
node --version || true
npm --version || true

# Virtualenv and basic Python deps
if [ -d .venv ]; then
  echo "Found .venv — checking key Python packages"
  . .venv/bin/activate >/dev/null 2>&1 || true
  python - <<PY || echo "Some Python packages may be missing; run 'python -m pip install -r requirements.txt'"
try:
    import uvicorn, sqlalchemy, pydantic
    print('Python core deps OK')
except Exception as e:
    print('Missing python deps:', e)
PY
else
  echo ".venv missing — create it with: python -m venv .venv && python -m pip install -r requirements.txt"
fi

# Node dev dependencies
if command -v node >/dev/null 2>&1; then
  echo "Checking root dev dependencies (concurrently)"
  if node -e "require('concurrently')" >/dev/null 2>&1; then
    echo "concurrently available at root"
  else
    echo "Root dev dependency 'concurrently' not installed (run 'npm ci' at repo root)"
  fi
  echo "Checking frontend tooling (openapi-typescript)"
  if (cd frontend && node -e "require('openapi-typescript')" >/dev/null 2>&1); then
    echo "openapi-typescript available in frontend"
  else
    echo "openapi-typescript missing in frontend (run 'cd frontend && npm ci')"
  fi
fi

echo
echo "[3/6] Ports listening (8000/5173)"
(ss -tulpen 2>/dev/null || netstat -tulpen 2>/dev/null || true) | grep -E '(:8000|:5173)' || echo "No ports 8000/5173 listening right now."

echo
echo "[4/6] Backend health"
if curl -s --max-time 2 http://localhost:8000/health >/dev/null; then
  curl -s http://localhost:8000/health; echo
  echo
  echo "[5/6] Backend version"
  curl -s http://localhost:8000/version; echo
else
  echo "Backend not reachable on http://localhost:8000 (is it running?)"
fi

echo
echo "[6/6] Frontend"
if curl -s --max-time 2 http://localhost:5173/ >/dev/null; then
  echo "Frontend reachable on http://localhost:5173"
else
  echo "Frontend not reachable on http://localhost:5173 (is it running?)"
fi

echo
echo "=== Done ==="
