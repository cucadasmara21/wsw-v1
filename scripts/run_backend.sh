#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -f "$ROOT/.venv/bin/activate" ]]; then 
# shellcheck disable=SC1091 
source "$ROOT/.venv/bin/activate"
fi
exec python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
