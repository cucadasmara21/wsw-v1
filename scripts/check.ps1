#!/usr/bin/env pwsh
# System check script for WallStreetWar dev environment

$ErrorActionPreference = "Continue"

$ROOT_DIR = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT_DIR

Write-Host "🔍 WallStreetWar Environment Check" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

$CHECKS_PASSED = 0
$CHECKS_FAILED = 0

function Check-Command {
    param($Command, $Name, $MinVersion)
    
    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        $version = & $Command --version 2>&1 | Select-Object -First 1
        Write-Host "✅ $Name`: $version" -ForegroundColor Green
        $script:CHECKS_PASSED++
        return $true
    } else {
        Write-Host "❌ $Name not found (expected: $MinVersion+)" -ForegroundColor Red
        $script:CHECKS_FAILED++
        return $false
    }
}

# Check Python
Write-Host "1️⃣  Checking Python..." -ForegroundColor White
$pythonFound = $false
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python: $pythonVersion" -ForegroundColor Green
    $CHECKS_PASSED++
    $pythonFound = $true
    
    # Check if venv exists
    if (Test-Path ".venv") {
        Write-Host "✅ Virtual environment: .venv exists" -ForegroundColor Green
        $CHECKS_PASSED++
        
        # Check if dependencies are installed
        if (Test-Path ".venv/Scripts/Activate.ps1") {
            & ".\.venv\Scripts\Activate.ps1"
            try {
                python -c "import fastapi" 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Host "✅ Python dependencies: FastAPI installed" -ForegroundColor Green
                    $CHECKS_PASSED++
                } else {
                    Write-Host "⚠️  Python dependencies: FastAPI not installed" -ForegroundColor Yellow
                    Write-Host "   Run: pip install -r requirements.txt" -ForegroundColor Gray
                    $CHECKS_FAILED++
                }
            } catch {
                Write-Host "⚠️  Python dependencies: FastAPI not installed" -ForegroundColor Yellow
                Write-Host "   Run: pip install -r requirements.txt" -ForegroundColor Gray
                $CHECKS_FAILED++
            }
        }
    } else {
        Write-Host "⚠️  Virtual environment: not created" -ForegroundColor Yellow
        Write-Host "   Run: python -m venv .venv" -ForegroundColor Gray
        $CHECKS_FAILED++
    }
} else {
    Write-Host "❌ Python not found" -ForegroundColor Red
    $CHECKS_FAILED++
}

Write-Host ""

# Check Node.js
Write-Host "2️⃣  Checking Node.js..." -ForegroundColor White
if (Check-Command "node" "Node.js" "18.0") {
    if (Get-Command npm -ErrorAction SilentlyContinue) {
        $npmVersion = npm --version
        Write-Host "✅ npm: $npmVersion" -ForegroundColor Green
        $CHECKS_PASSED++
    } else {
        Write-Host "❌ npm not found" -ForegroundColor Red
        $CHECKS_FAILED++
    }
    
    # Check frontend dependencies
    if (Test-Path "frontend/node_modules") {
        Write-Host "✅ Frontend dependencies: node_modules exists" -ForegroundColor Green
        $CHECKS_PASSED++
    } else {
        Write-Host "⚠️  Frontend dependencies: not installed" -ForegroundColor Yellow
        Write-Host "   Run: cd frontend && npm ci" -ForegroundColor Gray
        $CHECKS_FAILED++
    }
}

Write-Host ""

# Check database
Write-Host "3️⃣  Checking Database..." -ForegroundColor White
if (Test-Path "wsw.db") {
    $dbSize = (Get-Item "wsw.db").Length / 1KB
    Write-Host "✅ Database: wsw.db exists ($([math]::Round($dbSize, 2)) KB)" -ForegroundColor Green
    $CHECKS_PASSED++
} else {
    Write-Host "⚠️  Database: wsw.db not found" -ForegroundColor Yellow
    Write-Host "   Run: python init_db.py" -ForegroundColor Gray
    $CHECKS_FAILED++
}

# Check .env
if (Test-Path ".env") {
    Write-Host "✅ Configuration: .env exists" -ForegroundColor Green
    $CHECKS_PASSED++
} else {
    Write-Host "⚠️  Configuration: .env not found" -ForegroundColor Yellow
    Write-Host "   Run: Copy-Item .env.example .env" -ForegroundColor Gray
    $CHECKS_FAILED++
}

Write-Host ""

# Check ports
Write-Host "4️⃣  Checking Ports..." -ForegroundColor White
$PORT = if ($env:PORT) { $env:PORT } else { 8000 }
$VITE_PORT = 5173

function Check-Port {
    param($Port, $Name)
    
    try {
        $connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        if ($connection) {
            Write-Host "⚠️  Port $Port ($Name): BUSY" -ForegroundColor Yellow
            Write-Host "   Kill process: Get-Process -Id (Get-NetTCPConnection -LocalPort $Port).OwningProcess | Stop-Process" -ForegroundColor Gray
            return $false
        }
    } catch { }
    
    Write-Host "✅ Port $Port ($Name): available" -ForegroundColor Green
    return $true
}

if (Check-Port $PORT "backend") {
    $CHECKS_PASSED++
} else {
    $CHECKS_FAILED++
}

if (Check-Port $VITE_PORT "frontend") {
    $CHECKS_PASSED++
} else {
    $CHECKS_FAILED++
}

Write-Host ""

# Check backend health (if running)
Write-Host "5️⃣  Checking Backend..." -ForegroundColor White
try {
    $health = Invoke-RestMethod -Uri "http://localhost:$PORT/health" -TimeoutSec 3 -ErrorAction Stop
    Write-Host "✅ Backend: running at http://localhost:$PORT" -ForegroundColor Green
    Write-Host "   Status: $($health.status)" -ForegroundColor Gray
    $CHECKS_PASSED++
} catch {
    Write-Host "⚠️  Backend: not running" -ForegroundColor Yellow
    Write-Host "   Start with: .\scripts\dev.ps1" -ForegroundColor Gray
}

Write-Host ""
Write-Host "==================================" -ForegroundColor Cyan
Write-Host "Summary:" -ForegroundColor White
Write-Host "✅ Passed: $CHECKS_PASSED" -ForegroundColor Green

if ($CHECKS_FAILED -gt 0) {
    Write-Host "❌ Failed: $CHECKS_FAILED" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix the issues above and run this script again." -ForegroundColor Yellow
    exit 1
} else {
    Write-Host "🎉 All checks passed!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Ready to start development:" -ForegroundColor White
    Write-Host "  .\scripts\dev.ps1" -ForegroundColor Cyan
    exit 0
}
