#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Environment ==="
python --version || true
node --version || true
npm --version || true

check_port(){
  local port=$1
  echo "\nChecking port $port..."
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "sport = :$port" || true
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:$port -sTCP:LISTEN || true
  else
    echo "No ss or lsof available to check ports"
  fi
}

check_port 8000
check_port 5173

echo "\nIf a port is listed above, note the PID and use scripts/kill-ports.sh to terminate or use your OS tools to stop the process."

echo "\nTo free ports manually:"
echo "  Linux/Codespaces: lsof -n -i :8000 | awk 'NR>1{print \$2}' | xargs -r kill -9"
echo "  or: fuser -k 8000/tcp"
echo "  Windows (PowerShell): Get-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess | Stop-Process"