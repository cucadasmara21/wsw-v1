#!/usr/bin/env bash
set -euo pipefail

# Dev helper for Codespaces / Linux / Mac
# Starts backend (uvicorn) on PORT 8000 and frontend (vite) on 5173

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

: ${PORT:=8000}
VITE_PORT=5173

warn_if_busy() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn "sport = :$port" | grep -q LISTEN; then
      echo "⚠️  Port $port appears to be in use. Run scripts/doctor.sh to investigate."
    fi
  elif command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "⚠️  Port $port appears to be in use. Run scripts/doctor.sh to investigate."
    fi
  fi
}

warn_if_busy "$PORT"
warn_if_busy "$VITE_PORT"

echo "Creating/activating virtualenv .venv (Python 3.x)"
python -m venv .venv || true
# shellcheck source=/dev/null
. .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt

echo "Initializing database..."
python init_db.py

# Start backend in background
echo "Starting backend on http://127.0.0.1:$PORT"
python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --reload &
UV_PID=$!

sleep 1

# Start frontend with strictPort=true to fail early if 5173 is busy
echo "Starting frontend on http://0.0.0.0:$VITE_PORT (strictPort=true)"
(cd frontend && npm ci && npm run dev -- --host 0.0.0.0 --port $VITE_PORT --strictPort) &
VITE_PID=$!

echo "Backend PID: $UV_PID"
echo "Frontend PID: $VITE_PID"

echo "Dev environment started. Use 'kill $UV_PID $VITE_PID' to stop processes or run scripts/doctor.sh for guidance."