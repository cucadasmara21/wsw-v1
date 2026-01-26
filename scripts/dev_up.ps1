#!/usr/bin/env pwsh
param(
  [int]$Target = 5000,
  [string]$ApiBase = "http://127.0.0.1:8000",
  [string]$FrontendBase = "http://127.0.0.1:5173"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\\..")

Write-Host "=== dev_up: infra + backend + seed + verify ===" -ForegroundColor Cyan

# 1) Infra
Write-Host "[1/5] Starting Postgres via docker compose..." -ForegroundColor Gray
docker compose -f .\docker-compose.yml up -d | Out-Host

# 2) Env vars (both sync + async)
$env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/wsw_db"
$env:DATABASE_DSN_ASYNC = "postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"
Write-Host "[2/5] Set DATABASE_URL + DATABASE_DSN_ASYNC" -ForegroundColor Gray

# 3) Start backend in a new window
Write-Host "[3/5] Starting backend in new PowerShell window..." -ForegroundColor Gray
Start-Process -FilePath "pwsh" -ArgumentList @(
  "-NoExit",
  "-Command",
  "cd `"$PWD`"; `$env:DATABASE_URL=`"$env:DATABASE_URL`"; `$env:DATABASE_DSN_ASYNC=`"$env:DATABASE_DSN_ASYNC`"; .\scripts\run_backend.ps1"
) | Out-Null

# 4) (Optional) start frontend if present
if (Test-Path ".\\frontend\\package.json") {
  Write-Host "[3b] Starting frontend (Vite) in new PowerShell window..." -ForegroundColor Gray
  Start-Process -FilePath "pwsh" -ArgumentList @(
    "-NoExit",
    "-Command",
    "cd `"$PWD`"; npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173"
  ) | Out-Null
}

# Wait for backend to respond
Write-Host "[wait] Waiting for backend $ApiBase/health ..." -ForegroundColor Gray
$deadline = (Get-Date).AddSeconds(120)
do {
  try {
    $code = (curl.exe -s -o NUL -w "%{http_code}" "$ApiBase/health")
    if ($code -eq "200") { break }
  } catch { }
  Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

$code = (curl.exe -s -o NUL -w "%{http_code}" "$ApiBase/health")
if ($code -ne "200") {
  throw "Backend did not become healthy in time (status=$code)"
}
Write-Host "PASS: backend is up" -ForegroundColor Green

# 4) Seed universe (will auto-synthetic if source missing)
Write-Host "[4/5] Seeding universe_assets (target=$Target)..." -ForegroundColor Gray
python ".\\backend\\scripts\\seed_universe_v8.py" --target $Target --batch 1000 --verify

# 5) Verify endpoints
Write-Host "[5/5] Verifying endpoints..." -ForegroundColor Gray

function Assert-Http200([string]$Url, [string]$Label) {
  $status = (curl.exe -s -o NUL -w "%{http_code}" $Url)
  if ($status -ne "200") { throw "FAIL: $Label expected 200 got $status ($Url)" }
  Write-Host "PASS: $Label (200)" -ForegroundColor Green
}

Assert-Http200 "$ApiBase/api/universe/v8/health" "v8/health"

$snap = Join-Path $env:TEMP "v8_snapshot.bin"
curl.exe -s -o "$snap" "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=zstd"
if ((Get-Item $snap).Length -le 0) { throw "FAIL: v8 snapshot empty" }
Write-Host ("PASS: v8 snapshot bytes={0}" -f (Get-Item $snap).Length) -ForegroundColor Green

$pb = Join-Path $env:TEMP "points.bin"
curl.exe -s -o "$pb" "$ApiBase/api/universe/points.bin?limit=10000"
if ((Get-Item $pb).Length -le 0) { throw "FAIL: points.bin empty" }
Write-Host ("PASS: points.bin bytes={0}" -f (Get-Item $pb).Length) -ForegroundColor Green

Write-Host "=== ALL PASS ===" -ForegroundColor Green
Write-Host ("Open: {0}/universe" -f $FrontendBase) -ForegroundColor Cyan

