#!/usr/bin/env pwsh
# Dev helper for Windows (PowerShell)
# Starts backend (uvicorn) on PORT 8000 and frontend (vite) on 5173

$ErrorActionPreference = "Stop"

# Navigate to repo root
$ROOT_DIR = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT_DIR

Write-Host "🚀 WallStreetWar Dev Environment - Windows" -ForegroundColor Cyan
Write-Host ""

# Ensure Docker Compose Postgres is running (repo-root docker-compose.yml)
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Docker not found in PATH. Install Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

Write-Host "🐳 Starting PostgreSQL via docker compose..." -ForegroundColor Cyan
# If an old container_name-based instance exists, remove it to avoid conflicts.
try {
    $names = docker ps -a --format "{{.Names}}" 2>$null
    if ($names -and ($names -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -eq "wsw-postgres" })) {
        Write-Host "ℹ️  Removing legacy container 'wsw-postgres' to avoid name/port conflicts..." -ForegroundColor Yellow
        docker rm -f wsw-postgres | Out-Host
    }
} catch { }

docker compose up -d --remove-orphans | Out-Host

Write-Host "⏳ Waiting for postgres health..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Date) -lt $deadline) {
    try {
        $cid = (docker compose ps -q wsw-postgres 2>$null).Trim()
        if (-not $cid) { Start-Sleep -Seconds 2; continue }
        $health = (docker inspect --format='{{.State.Health.Status}}' $cid 2>$null)
        if ($health -eq "healthy") { break }
    } catch { }
    Start-Sleep -Seconds 2
}
$cid = (docker compose ps -q wsw-postgres 2>$null).Trim()
$health = ""
if ($cid) { $health = (docker inspect --format='{{.State.Health.Status}}' $cid 2>$null) }
if ($health -ne "healthy") {
    Write-Host "❌ Postgres container not healthy. Check logs:" -ForegroundColor Red
    Write-Host "   docker compose logs -f wsw-postgres" -ForegroundColor Yellow
    exit 1
}
Write-Host "✅ Postgres healthy (wsw-postgres)" -ForegroundColor Green

# Force deterministic local DSN for backend (host connects to container via published port)
$dsn = "postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"
$env:DATABASE_URL = $dsn
$env:DATABASE_DSN_ASYNC = $dsn
$env:ENABLE_TIMESCALE = "false"

# Check Python
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Python not found in PATH. Install Python 3.12+ and try again." -ForegroundColor Red
    exit 1
}

$pythonVersion = python --version 2>&1
Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green

# Check Node
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "❌ Node.js not found in PATH. Install Node.js 18+ and try again." -ForegroundColor Red
    exit 1
}

$nodeVersion = node --version
Write-Host "✅ Node.js: $nodeVersion" -ForegroundColor Green
Write-Host ""

# Backend port check
$PORT = if ($env:PORT) { $env:PORT } else { 8000 }
try {
    $portCheck = Get-NetTCPConnection -LocalPort $PORT -ErrorAction SilentlyContinue
    if ($portCheck) {
        Write-Host "❌ Port $PORT is busy. Kill the process:" -ForegroundColor Red
        Write-Host "   Get-Process -Id (Get-NetTCPConnection -LocalPort $PORT).OwningProcess | Stop-Process" -ForegroundColor Yellow
        exit 1
    }
} catch { }

# Frontend port check
$VITE_PORT = 5173
try {
    $vitePortCheck = Get-NetTCPConnection -LocalPort $VITE_PORT -ErrorAction SilentlyContinue
    if ($vitePortCheck) {
        Write-Host "❌ Port $VITE_PORT is busy. Kill the process:" -ForegroundColor Red
        Write-Host "   Get-Process -Id (Get-NetTCPConnection -LocalPort $VITE_PORT).OwningProcess | Stop-Process" -ForegroundColor Yellow
        exit 1
    }
} catch { }

# Check .env file
if (-not (Test-Path ".env")) {
    Write-Host "⚠️  .env file not found. Copying from .env.example..." -ForegroundColor Yellow
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "✅ Created .env from .env.example" -ForegroundColor Green
        Write-Host "   Review .env and adjust settings if needed." -ForegroundColor Cyan
    } else {
        Write-Host "❌ .env.example not found. Create .env manually." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "📦 Setting up Python environment..." -ForegroundColor Cyan

# Create venv if missing
if (-not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}

# Activate venv
Write-Host "Activating virtual environment..."
& ".\.venv\Scripts\Activate.ps1"

# Upgrade pip
Write-Host "Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install dependencies
Write-Host "Installing Python dependencies..."
pip install -r requirements.txt --quiet

# Initialize database
Write-Host ""
Write-Host "🗄️  Initializing database..." -ForegroundColor Cyan
python init_db.py

Write-Host ""
Write-Host "📦 Setting up frontend..." -ForegroundColor Cyan
Set-Location frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing npm dependencies..."
    npm ci --silent
} else {
    Write-Host "✅ node_modules already installed" -ForegroundColor Green
}
Set-Location ..

Write-Host ""
Write-Host "🚀 Starting services..." -ForegroundColor Cyan
Write-Host "   Backend:  http://localhost:$PORT" -ForegroundColor Green
Write-Host "   Frontend: http://localhost:$VITE_PORT" -ForegroundColor Green
Write-Host "   V8 Health: http://localhost:$PORT/api/universe/v8/health" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
Write-Host ""

# Start backend in new window for easier visibility
$backendCmd = "cd '$ROOT_DIR'; `$env:DATABASE_URL='$dsn'; `$env:DATABASE_DSN_ASYNC='$dsn'; .\.venv\Scripts\Activate.ps1; python -m uvicorn main:app --host 127.0.0.1 --port $PORT --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# Wait for backend health (up to 60s)
Write-Host "⏳ Waiting for backend http://127.0.0.1:$PORT/health ..." -ForegroundColor Cyan
$backendDeadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $backendDeadline) {
    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/health" -TimeoutSec 2
        break
    } catch {
        Start-Sleep -Seconds 2
    }
}

# Start frontend in new window
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT_DIR\frontend'; npm run dev -- --host 127.0.0.1 --port $VITE_PORT"

# Wait and check health
Start-Sleep -Seconds 3

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/health" -TimeoutSec 5
    Write-Host "✅ Backend health check passed" -ForegroundColor Green
    Write-Host "   Status: $($health.status)" -ForegroundColor Gray
} catch {
    Write-Host "⚠️  Backend health check failed. Check the backend window for errors." -ForegroundColor Yellow
}

try {
    $v8 = Invoke-RestMethod -Uri "http://127.0.0.1:$PORT/api/universe/v8/health" -TimeoutSec 5
    Write-Host "✅ V8 health endpoint reachable" -ForegroundColor Green
    Write-Host "   status=$($v8.status) scheme=$($v8.database_url_scheme) v8_ready=$($v8.v8_ready)" -ForegroundColor Gray
} catch {
    Write-Host "⚠️  V8 health check failed. Backend may still be starting." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "================================" -ForegroundColor Cyan
Write-Host "🎉 Development environment ready!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Open in browser:" -ForegroundColor White
Write-Host "  Frontend: http://localhost:$VITE_PORT" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:$PORT/docs" -ForegroundColor Cyan
Write-Host "  Health:   http://localhost:$PORT/health" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verify (PowerShell):" -ForegroundColor White
Write-Host "  curl.exe -i http://127.0.0.1:$PORT/api/universe/v8/health" -ForegroundColor Gray
Write-Host "  curl.exe -I \"http://127.0.0.1:$PORT/api/universe/v8/snapshot?format=vertex28&compression=zstd\"" -ForegroundColor Gray
Write-Host ""
Write-Host "Close the PowerShell windows to stop services" -ForegroundColor Yellow