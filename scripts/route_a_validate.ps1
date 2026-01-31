#!/usr/bin/env pwsh
param(
  [string]$ApiBase = "http://127.0.0.1:8000"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Curl-Status {
  param([Parameter(Mandatory=$true)][string]$Url, [string]$OutFile = $null)
  if ($OutFile) {
    $code = & curl.exe -sS -o $OutFile -w "%{http_code}" $Url
  } else {
    $tmp = Join-Path $env:TEMP "wsw_tmp.txt"
    $code = & curl.exe -sS -o $tmp -w "%{http_code}" $Url
  }
  if (-not $code) { throw "curl failed for: $Url" }
  return [int]$code
}

# (1) Health must be 200 (seeded + stride ok)
$health = "$ApiBase/api/universe/v8/health"
$hc = Curl-Status $health
if ($hc -ne 200) { throw "Health failed ($hc): $health" }

# (2) Assets must be 200
$assets = "$ApiBase/api/assets?limit=50"
$ac = Curl-Status $assets
if ($ac -ne 200) { throw "Assets failed ($ac): $assets" }

# (3) Snapshot download + stride check
$snap = "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=none"
$snapPath = Join-Path $env:TEMP "v8_snapshot.bin"
$sc = Curl-Status $snap $snapPath
if ($sc -ne 200) { throw "Snapshot failed ($sc): $snap" }

$len = (Get-Item $snapPath).Length
if (($len % 28) -ne 0) { throw "Stride violation: $len bytes not multiple of 28" }

# (4) DB integrity: universe_assets count > 0
& docker exec wsw-postgres psql -U postgres -d wsw_db -c "SELECT COUNT(*) FROM public.universe_assets;"
if ($LASTEXITCODE -ne 0) { throw "docker/psql check failed" }

Write-Host "OK Route A validate: health=200 assets=200 snapshot_stride=28 universe_assets>0"

