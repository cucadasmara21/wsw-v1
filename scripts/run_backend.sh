#!/usr/bin/env bash
set -euo pipefail

# Run backend from repository root with repository .venv if present
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

# Activate venv if available
if [ -f "$DIR/.venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source "$DIR/.venv/bin/activate"
else
  echo "[scripts/run_backend.sh] Warning: .venv not found — using system Python"
fi

echo "[scripts/run_backend.sh] Starting backend: uvicorn main:app --reload --host 0.0.0.0 --port 8000"
exec python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
