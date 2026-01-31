param(
  [int]$Target = 200000,
  [string]$ApiBase = "http://127.0.0.1:8000",
  [string]$PgContainer = "wsw-postgres",
  [string]$Db = "wsw_db",
  [string]$User = "postgres",
  [int]$Runs = 7
)

$ErrorActionPreference = "Stop"

function Resolve-PgContainerId {
  param([string]$Name)
  try {
    $id = (docker ps -aq --filter "name=^/$Name$" 2>$null).Trim()
    if ($id) { return $id }
  } catch { }

  # Fallback: docker compose service container
  try {
    $id = (docker compose ps -q wsw-postgres 2>$null).Trim()
    if ($id) { return $id }
  } catch { }

  throw "Postgres container not found. Tried name '$Name' and 'docker compose ps -q wsw-postgres'."
}

function Invoke-PsqlScalar {
  param(
    [string]$ContainerId,
    [string]$Sql
  )
  $cmd = "psql -U $User -d $Db -t -A -c ""$Sql"""
  $out = (docker exec -i $ContainerId sh -lc $cmd) | Out-String
  return $out.Trim()
}

Write-Host "=== TITAN V8 Deep-Scan Audit ===" -ForegroundColor Cyan
Write-Host ("Target: {0}" -f $Target) -ForegroundColor Gray
Write-Host ("API:    {0}" -f $ApiBase) -ForegroundColor Gray

$pgId = Resolve-PgContainerId -Name $PgContainer
Write-Host ("Postgres container: {0}" -f $pgId) -ForegroundColor Gray

# ---------------------------------------------------------------------
# 0) API health validation
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "0) API health (/api/universe/v8/health)" -ForegroundColor Cyan

$healthUrl = "$ApiBase/api/universe/v8/health"
try {
  $healthResp = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -Method GET -TimeoutSec 10
  $healthJson = $healthResp.Content | ConvertFrom-Json
  Write-Host ("HTTP {0}" -f $healthResp.StatusCode) -ForegroundColor Gray
  Write-Host ("status={0} v8_ready={1} scheme={2}" -f $healthJson.status, $healthJson.v8_ready, $healthJson.database_url_scheme) -ForegroundColor Gray
  if (-not $healthJson.v8_ready) { throw "FAIL: V8 not ready. See remediation in response." }
} catch {
  Write-Host ("FAIL: V8 health check failed: {0}" -f $_) -ForegroundColor Red
  exit 2
}

# ---------------------------------------------------------------------
# A) Integrity validation
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "A) Integrity validation (public.universe_assets)" -ForegroundColor Cyan

$sql = @"
SELECT
  COUNT(*)::bigint AS n,
  SUM(CASE WHEN octet_length(vertex_buffer) = 28 THEN 1 ELSE 0 END)::bigint AS ok,
  MIN(octet_length(vertex_buffer))::int AS min_len,
  MAX(octet_length(vertex_buffer))::int AS max_len
FROM public.universe_assets;
"@

$raw = Invoke-PsqlScalar -ContainerId $pgId -Sql $sql
$parts = $raw -split "\|"
if ($parts.Length -lt 4) {
  throw "Unexpected psql output: '$raw'"
}

$n = [int64]$parts[0]
$ok = [int64]$parts[1]
$minLen = [int]$parts[2]
$maxLen = [int]$parts[3]

Write-Host ("rows={0} ok28={1} min={2} max={3}" -f $n, $ok, $minLen, $maxLen) -ForegroundColor Gray

if ($n -ne $Target) { throw "FAIL: rowcount mismatch: expected $Target got $n" }
if ($ok -ne $n) { throw "FAIL: stride mismatch: ok28=$ok rows=$n" }
if ($minLen -ne 28 -or $maxLen -ne 28) { throw "FAIL: vertex_buffer length min/max != 28" }

# Morton collision check
$mortonOk = Invoke-PsqlScalar -ContainerId $pgId -Sql "SELECT (COUNT(*) = COUNT(DISTINCT morton_code)) FROM public.universe_assets;"
if ($mortonOk -notmatch "t|true|1") { throw "FAIL: morton_code collisions detected" }
Write-Host "PASS: Vertex28 stride + morton uniqueness" -ForegroundColor Green

# ---------------------------------------------------------------------
# B) Snapshot latency/throughput measurement
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "B) Snapshot latency/throughput measurement" -ForegroundColor Cyan

$urlRaw = "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=none&limit=$Target"
$urlZstd = "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=zstd&limit=$Target"

Write-Host ("GET (raw)  {0}" -f $urlRaw) -ForegroundColor Gray
Write-Host ("GET (zstd) {0}" -f $urlZstd) -ForegroundColor Gray
Write-Host ("Runs: {0}" -f $Runs) -ForegroundColor Gray

if ($Runs -lt 3) { throw "Runs must be >= 3 for p50/p95 estimates." }

$times = @()
$bytesObserved = $null
for ($i=1; $i -le $Runs; $i++) {
  $tmp = Join-Path $env:TEMP ("titan_v8_snapshot_{0}_{1}.bin" -f $i, ([Guid]::NewGuid().ToString("N")))
  $t = Measure-Command {
    & curl.exe -sS -o $tmp $urlRaw | Out-Null
  }
  $bytes = (Get-Item $tmp).Length
  Remove-Item $tmp -Force

  if ($bytesObserved -eq $null) { $bytesObserved = $bytes }
  if ($bytes -ne $bytesObserved) { throw "FAIL: snapshot size changed across runs: first=$bytesObserved current=$bytes" }

  $sec = [Math]::Max(0.001, $t.TotalSeconds)
  $times += $sec
  Write-Host ("run {0}/{1}: {2:N3}s" -f $i, $Runs, $sec) -ForegroundColor Gray
}

$sorted = $times | Sort-Object
function Percentile([double[]]$xs, [double]$p) {
  $n = $xs.Length
  $idx = [Math]::Floor(($n - 1) * $p)
  return $xs[[int]$idx]
}

$p50 = Percentile -xs $sorted -p 0.50
$p95 = Percentile -xs $sorted -p 0.95

$records = [double]$bytesObserved / 28.0
$mb = [double]$bytesObserved / 1024.0 / 1024.0
$rps50 = $records / $p50
$mbps50 = $mb / $p50
$rps95 = $records / $p95
$mbps95 = $mb / $p95

Write-Host ("bytes={0} records={1:N0}" -f $bytesObserved, [int64]$records) -ForegroundColor Gray
Write-Host ("p50={0:N3}s  => {1:N0} records/s, {2:N1} MiB/s" -f $p50, $rps50, $mbps50) -ForegroundColor Green
Write-Host ("p95={0:N3}s  => {1:N0} records/s, {2:N1} MiB/s" -f $p95, $rps95, $mbps95) -ForegroundColor Green

# zstd latency smoke (status + ms)
Write-Host ""
Write-Host "B2) Snapshot zstd latency smoke" -ForegroundColor Cyan
$tmpZ = Join-Path $env:TEMP ("titan_v8_snapshot_zstd_{0}.bin" -f ([Guid]::NewGuid().ToString("N")))
$tZ = Measure-Command {
  & curl.exe -sS -D - -o $tmpZ $urlZstd | Out-Null
}
$bytesZ = (Get-Item $tmpZ).Length
Remove-Item $tmpZ -Force
Write-Host ("zstd bytes={0} seconds={1:N3}" -f $bytesZ, $tZ.TotalSeconds) -ForegroundColor Gray

# ---------------------------------------------------------------------
# C) VRAM simulation
# ---------------------------------------------------------------------
Write-Host ""
Write-Host "C) VRAM simulation (Vertex28)" -ForegroundColor Cyan

$bufBytes = [int64]$Target * 28
$bufMb = [double]$bufBytes / 1024.0 / 1024.0
$bufMbOver = $bufMb * 1.2

Write-Host ("GPU buffer bytes: {0:N0} ({1:N1} MiB)" -f $bufBytes, $bufMb) -ForegroundColor Gray
Write-Host ("Estimated overhead (+20%): {0:N1} MiB" -f $bufMbOver) -ForegroundColor Gray

Write-Host ""
Write-Host "PASS: Audit complete" -ForegroundColor Green
exit 0

