#!/usr/bin/env bash
set -euo pipefail

# Kill uvicorn and vite/node processes bound to ports 8000 and 5173.
# First try pkill by process name (uvicorn, vite, npm, node)
# Then fallback to lsof to find PIDs bound to the port.

echo "[scripts/kill_ports.sh] Killing uvicorn and vite/node processes (ports 8000, 5173)"

# pkill patterns (ignore errors)
pkill -f uvicorn || true
pkill -f "vite" || true
pkill -f "npm run dev" || true
pkill -f "node" || true

# Fallback: lsof -t to find PIDs and kill if still present
if command -v lsof >/dev/null 2>&1; then
  for p in 8000 5173; do
    pids=$(lsof -t -i :${p} || true)
    if [ -n "$pids" ]; then
      echo "[scripts/kill_ports.sh] Killing PIDs on port ${p}: $pids"
      kill -9 $pids || true
    fi
  done
else
  echo "[scripts/kill_ports.sh] lsof not available; pkill attempted only"
fi

echo "[scripts/kill_ports.sh] Done."
