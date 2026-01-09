#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
source .venv/bin/activate

echo "▶ Starting backend (FastAPI) on :8000"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
