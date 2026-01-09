#!/usr/bin/env bash
set -euo pipefail

# Non-destructive by default: shows what would be killed
# Use --yes to actually kill

yes=false
for arg in "$@"; do
  if [[ "$arg" == "--yes" ]]; then
    yes=true
  fi
done

kill_if_confirm(){
  local port=$1
  echo "Checking port $port..."
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -t -iTCP:$port -sTCP:LISTEN || true)
    if [[ -n "$pids" ]]; then
      echo "Would kill PIDs on port $port: $pids"
      if $yes; then
        echo "Killing $pids"
        echo "$pids" | xargs -r kill -9
      fi
    else
      echo "No process listening on $port"
    fi
  else
    echo "lsof not available; cannot determine PIDs"
  fi
}

kill_if_confirm 8000
kill_if_confirm 5173

if ! $yes; then
  echo "\nRun with --yes to actually kill the processes (destructive)."
fi