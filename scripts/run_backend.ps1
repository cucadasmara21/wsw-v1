#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\\..")

if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/wsw_db"
}
if (-not $env:DATABASE_DSN_ASYNC) {
  $env:DATABASE_DSN_ASYNC = "postgresql://postgres:postgres@127.0.0.1:5432/wsw_db"
}

Write-Host "[backend] DATABASE_URL scheme set (value redacted)"
Write-Host "[backend] Starting uvicorn on 127.0.0.1:8000"

python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

