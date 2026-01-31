#!/usr/bin/env pwsh
# Canonical frontend startup script for Windows
# Starts Vite dev server on :5173

$ErrorActionPreference = "Stop"

# Navigate to repo root
$ROOT_DIR = Split-Path -Parent $PSScriptRoot
$FRONTEND_DIR = Join-Path $ROOT_DIR "frontend"

if (-not (Test-Path $FRONTEND_DIR)) {
    Write-Host "❌ Frontend directory not found: $FRONTEND_DIR" -ForegroundColor Red
    exit 1
}

Set-Location $FRONTEND_DIR

Write-Host "🎨 Starting WallStreetWar Frontend" -ForegroundColor Cyan
Write-Host ""

# Check Node
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Node.js not found in PATH. Install Node.js 18+ and try again." -ForegroundColor Red
    exit 1
}

# Install dependencies if needed
if (-not (Test-Path "node_modules")) {
    Write-Host "📦 Installing npm dependencies..." -ForegroundColor Cyan
    npm ci
}

Write-Host "🔌 Starting Vite dev server on 127.0.0.1:5173..." -ForegroundColor Cyan
Write-Host "   Frontend: http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "   Backend proxy: /api -> http://127.0.0.1:8000" -ForegroundColor Gray
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start Vite
npm run dev
