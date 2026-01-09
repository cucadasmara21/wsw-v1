#!/usr/bin/env bash
set -euo pipefail
kill_port() { 
local PORT="$1" 
if command -v lsof >/dev/null 2>&1; then 
local PIDS 
PIDS="$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | sort -u || true)" 
if [[ -z "$PIDS" ]]; then 
echo "[ports] $PORT free" 
return 0 
fi 
for PID in $PIDS; do 
local ARGS 
ARGS="$(ps -p "$PID" -o args= 2>/dev/null || true)" 
# Only kill related things (uvicorn/vite/npm dev) 
if [[ "$ARGS" == *"uvicorn"* || "$ARGS" == *"vite"* || "$ARGS" == *"npm run dev"* ]]; then 
echo "[ports] Killing PID $PID in $PORT: $ARGS" 
kill -9 "$PID" 2>/dev/null || true 
else 
echo "[ports] DON'T kill PID $PID in $PORT (doesn't look like uvicorn/vite): $ARGS" 
fi 
done 
else 
echo "[ports] lsof not available, fallback pkill" 
fi 

# Fallback by pattern (without killing generic 'node') 
pkill -f "uvicorn.*--port 8000" 2>/dev/null || true 
pkill -f "vite.*5173" 2>/dev/null || true 
pkill -f "npm run dev.*5173" 2>/dev/null || true
}
kill_port 8000
kill_port 5173
echo "[ports] done"
