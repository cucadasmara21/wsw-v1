#!/usr/bin/env pwsh
# Dev helper for Windows (PowerShell)
# Starts backend (uvicorn) on PORT 8000 and frontend (vite) on 5173

$ErrorActionPreference = "Stop"

# Navigate to repo root
$ROOT_DIR = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT_DIR

Write-Host "🚀 WallStreetWar Dev Environment - Windows" -ForegroundColor Cyan
Write-Host ""

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
Write-Host ""
Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
Write-Host ""

# Start backend in new window for easier visibility
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$ROOT_DIR'; .\.venv\Scripts\Activate.ps1; python -m uvicorn main:app --host 127.0.0.1 --port $PORT --reload"

# Wait for backend
Start-Sleep -Seconds 4

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
Write-Host "Close the PowerShell windows to stop services" -ForegroundColor Yellow