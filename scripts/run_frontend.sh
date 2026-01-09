#!/usr/bin/env bash
set -euo pipefail

# Run frontend dev server (Vite) from frontend directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR/frontend"

echo "[scripts/run_frontend.sh] Starting frontend: npm run dev -- --host 0.0.0.0 --port 5173"
exec npm run dev -- --host 0.0.0.0 --port 5173
