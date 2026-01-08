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

# Determine Vite port: prefer $VITE_PORT, but if busy pick a free one
echo "Starting frontend on available port (preferred $VITE_PORT)"

if ss -ltn "sport = :$VITE_PORT" | grep -q LISTEN >/dev/null 2>&1; then
  echo "⚠️  Preferred Vite port $VITE_PORT is busy. Selecting a free port."
  FREE_PORT=$(python - <<PY
import socket
s=socket.socket()
s.bind(("127.0.0.1",0))
port=s.getsockname()[1]
s.close()
print(port)
PY
)
  VITE_ACTUAL_PORT=$FREE_PORT
else
  VITE_ACTUAL_PORT=$VITE_PORT
fi

# Start frontend
echo "Starting frontend on http://0.0.0.0:$VITE_ACTUAL_PORT"
(cd frontend && npm ci && npm run dev -- --host 0.0.0.0 --port $VITE_ACTUAL_PORT) &
VITE_PID=$!

# Brief health checks
sleep 1

echo "Backend PID: $UV_PID"
echo "Frontend PID: $VITE_PID"

# Wait and perform health checks
sleep 2

echo "Checking backend health at http://127.0.0.1:$PORT/health"
if curl -sS http://127.0.0.1:$PORT/health | jq . >/dev/null 2>&1; then
  echo "✅ Backend healthy: http://127.0.0.1:$PORT/health"
else
  echo "⚠️  Backend may not be healthy yet; check logs or try again."
fi

# Check frontend index
echo "Checking frontend at http://127.0.0.1:$VITE_ACTUAL_PORT"
if curl -sS http://127.0.0.1:$VITE_ACTUAL_PORT | grep -q "<!doctype html>" >/dev/null 2>&1; then
  echo "✅ Frontend available: http://127.0.0.1:$VITE_ACTUAL_PORT"
else
  echo "⚠️  Frontend may not be reachable yet. Check Vite logs for errors or occupied ports."
fi

echo "Dev environment started. Use 'kill $UV_PID $VITE_PID' to stop processes or run scripts/doctor.sh for guidance."