#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../frontend"
echo "▶ Starting frontend (Vite) on :5173"
npm run dev -- --port 5173
