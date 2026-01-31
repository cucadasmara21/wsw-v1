#!/usr/bin/env pwsh
param()

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot
if (-not (Test-Path ".\\docker-compose.yml")) {
  Write-Error "docker-compose.yml not found in repo root. Run this script from the repo root."
  exit 1
}

Write-Host "=== TITAN V8 infra fix (deterministic) ===" -ForegroundColor Cyan

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Error "docker not found in PATH. Install Docker Desktop."
  exit 1
}

Write-Host "Stopping compose stack..." -ForegroundColor Gray
docker compose -f .\docker-compose.yml down --remove-orphans | Out-Host

Write-Host "Removing conflicting containers (ignore errors)..." -ForegroundColor Gray
$conflicts = @(
  "wsw-postgres",
  "wsw-v1-wsw-postgres-1",
  "wsw-wsw-postgres-1"
)
foreach ($name in $conflicts) {
  try { docker rm -f $name | Out-Null } catch { }
}

Write-Host "Starting Postgres..." -ForegroundColor Gray
docker compose -f .\docker-compose.yml up -d | Out-Host

$deadline = (Get-Date).AddSeconds(120)
$cid = ""
Write-Host "Waiting for Postgres to become healthy (timeout 120s)..." -ForegroundColor Gray
while ((Get-Date) -lt $deadline) {
  try {
    $cid = (docker ps -q --filter "name=^/wsw-postgres$" 2>$null).Trim()
    if (-not $cid) { Start-Sleep -Seconds 2; continue }
    $health = (docker inspect --format='{{.State.Health.Status}}' $cid 2>$null).Trim()
    if ($health -eq "healthy") { break }
  } catch { }
  Start-Sleep -Seconds 2
}

if (-not $cid) {
  Write-Error "Postgres container 'wsw-postgres' is not running."
  Write-Host "docker compose ps:" -ForegroundColor Yellow
  docker compose -f .\docker-compose.yml ps | Out-Host
  exit 2
}

$health = (docker inspect --format='{{.State.Health.Status}}' $cid 2>$null).Trim()
if ($health -ne "healthy") {
  Write-Error "Postgres container is not healthy (status=$health). Check logs:"
  Write-Host "  docker logs -f wsw-postgres" -ForegroundColor Yellow
  exit 3
}

Write-Host ("Postgres container: wsw-postgres ({0})" -f $cid) -ForegroundColor Green
Write-Host "Mapped port: 5432 -> 5432" -ForegroundColor Green

Write-Host "Connectivity smoke test (SELECT 1)..." -ForegroundColor Gray
docker exec -it wsw-postgres psql -U postgres -d wsw_db -c "SELECT 1;" | Out-Host

Write-Host "PASS: infra is healthy" -ForegroundColor Green
exit 0

