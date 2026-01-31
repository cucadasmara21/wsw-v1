#!/usr/bin/env pwsh
# Canonical backend startup script for Windows
# Sets DATABASE_URL from .env if present, starts uvicorn on :8000

$ErrorActionPreference = "Stop"

# Navigate to repo root
$ROOT_DIR = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT_DIR

Write-Host "🚀 Starting WallStreetWar Backend" -ForegroundColor Cyan
Write-Host ""

# Load .env if present
$envPath = Join-Path $ROOT_DIR ".env"
if (Test-Path $envPath) {
    Write-Host "📄 Loading .env from: $envPath" -ForegroundColor Gray
    Get-Content $envPath | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $key = $matches[1].Trim()
            $value = $matches[2].Trim()
            if (-not [string]::IsNullOrWhiteSpace($key)) {
                [Environment]::SetEnvironmentVariable($key, $value, "Process")
            }
        }
    }
} else {
    Write-Host "⚠️  .env not found at: $envPath" -ForegroundColor Yellow
    Write-Host "   DATABASE_URL will be taken from environment (or defaulted below)." -ForegroundColor Yellow
}

# Ensure DATABASE_URL is set (fallback to postgres if not set)
if (-not $env:DATABASE_URL) {
    Write-Host "⚠️  DATABASE_URL not set. Using default PostgreSQL DSN for local dev" -ForegroundColor Yellow
    $env:DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"
}

# Parse and log scheme
$dbUrl = $env:DATABASE_URL
$scheme = "unknown"
if ($dbUrl -match '^(\w+)://') {
    $scheme = $matches[1].ToLower()
}

# Redact password for logging
$redacted = $dbUrl
if ($dbUrl -match '^([^:]+)://([^:]+):([^@]+)@(.+)$') {
    $redacted = "$($matches[1])://$($matches[2]):***@$($matches[4])"
}

Write-Host "🗄️  DATABASE_URL scheme: $scheme" -ForegroundColor $(if ($scheme -eq "postgresql" -or $scheme -eq "postgres") { "Green" } else { "Yellow" })
Write-Host "🗄️  DATABASE_URL (redacted): $redacted" -ForegroundColor Gray

if ($scheme -eq "sqlite") {
    Write-Host "⚠️  WARNING: SQLite detected. TITAN V8 endpoints will be unavailable (503)." -ForegroundColor Yellow
    Write-Host "   Set DATABASE_URL to PostgreSQL DSN to enable V8." -ForegroundColor Yellow
} elseif ($scheme -eq "postgresql" -or $scheme -eq "postgres") {
    Write-Host "✅ PostgreSQL detected. TITAN V8 endpoints will be available." -ForegroundColor Green
}

Write-Host ""
Write-Host "🔌 Starting uvicorn on 0.0.0.0:8000..." -ForegroundColor Cyan
Write-Host "   Backend: http://localhost:8000" -ForegroundColor Green
Write-Host "   Docs:    http://localhost:8000/docs" -ForegroundColor Green
Write-Host "   Health:  http://localhost:8000/health" -ForegroundColor Green
Write-Host "   V8 Health: http://localhost:8000/api/universe/v8/health" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Start uvicorn
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
