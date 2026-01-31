#!/usr/bin/env pwsh
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

param(
  [string]$ApiBase = "http://127.0.0.1:8000"
)

function Invoke-CurlWithStatus {
  param(
    [Parameter(Mandatory=$true)][string]$Url,
    [Parameter(Mandatory=$true)][string]$OutFile
  )

  $code = & curl.exe -sS -o $OutFile -w "%{http_code}" $Url
  if (-not $code) { throw "curl failed to return a status code for: $Url" }
  return [int]$code
}

# DoD (1): Health must be 200 when Postgres reachable
$healthUrl = "$ApiBase/api/universe/v8/health"
$healthTmp = Join-Path $env:TEMP "wsw_v8_health.json"
$healthCode = Invoke-CurlWithStatus -Url $healthUrl -OutFile $healthTmp
if ($healthCode -ne 200) {
  Write-Host "FAIL health ($healthCode): $healthUrl"
  if (Test-Path $healthTmp) { Get-Content $healthTmp | Write-Host }
  exit 1
}
Write-Host "OK health (200): $healthUrl"

# DoD (2): Snapshot payload must be N*28 bytes (Vertex28)
$snapUrl = "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=none"
$snapPath = Join-Path $env:TEMP "v8_snapshot.bin"
$snapCode = Invoke-CurlWithStatus -Url $snapUrl -OutFile $snapPath
if ($snapCode -ne 200) {
  Write-Host "FAIL snapshot ($snapCode): $snapUrl"
  if (Test-Path $snapPath) { Get-Content $snapPath | Write-Host }
  exit 2
}

$len = (Get-Item $snapPath).Length
if (($len % 28) -ne 0) {
  Write-Host "FAIL stride: file length $len is not multiple of 28"
  exit 3
}

Write-Host "OK snapshot stride: $snapPath ($len bytes, stride=28)"
exit 0

