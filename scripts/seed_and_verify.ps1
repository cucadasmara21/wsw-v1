#!/usr/bin/env pwsh
param(
  [int]$Target = 5000,
  [string]$ApiBase = "http://127.0.0.1:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\\..")

Write-Host "[seed] Seeding universe_assets (synthetic if source_assets missing)..." -ForegroundColor Cyan
python ".\\backend\\scripts\\seed_universe_v8.py" --target $Target --batch 5000 --verify

Write-Host "[verify] Checking V8 health..." -ForegroundColor Cyan
$h = (curl.exe -s -i "$ApiBase/api/universe/v8/health")
if ($h -notmatch "200") {
  Write-Host $h
  throw "FAIL: v8/health not 200"
}
Write-Host "PASS: v8/health 200" -ForegroundColor Green

Write-Host "[verify] Checking V8 snapshot (expect 200 + non-empty, stride=28)..." -ForegroundColor Cyan
$out = Join-Path $env:TEMP "v8_snapshot.bin"
curl.exe -s -D "$out.headers" -o "$out" "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=none"
$len = (Get-Item $out).Length
if ($len -le 0) { throw "FAIL: v8 snapshot body empty" }
if (($len % 28) -ne 0) { throw "FAIL: v8 snapshot length not multiple of 28 (len=$len)" }
Write-Host ("PASS: v8 snapshot bytes={0}" -f $len) -ForegroundColor Green

Write-Host "ALL PASS" -ForegroundColor Green

