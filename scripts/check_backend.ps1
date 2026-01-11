# Backend Test Script (PowerShell)
# Cross-platform test runner for Windows

Write-Host "🧪 Backend Test Suite" -ForegroundColor Cyan
Write-Host "====================" -ForegroundColor Cyan

# Check if pytest is installed
try {
    $null = Get-Command pytest -ErrorAction Stop
} catch {
    Write-Host "❌ pytest not found. Installing test dependencies..." -ForegroundColor Yellow
    pip install -q -r requirements-dev.txt
}

Write-Host ""
Write-Host "Running pytest..." -ForegroundColor White
python -m pytest -v --tb=short

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Backend tests passed!" -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "❌ Backend tests failed!" -ForegroundColor Red
    exit 1
}
