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
  if (-not $code) { throw "curl failed: $Url" }
  return [int]$code
}

Write-Host "ROUTE A verify against $ApiBase"

# 1) health: must be 200 and v8_ready true
$health = "$ApiBase/api/universe/v8/health"
$hc = Curl-Status $health
if ($hc -ne 200) { throw "health not 200 ($hc): $health" }
$healthJson = & curl.exe -sS $health | ConvertFrom-Json
if ($healthJson.v8_ready -ne $true) { throw "health v8_ready is not true" }

# 2) tree: must be 200
$tree = "$ApiBase/api/universe/tree"
$tc = Curl-Status $tree
if ($tc -ne 200) { throw "tree not 200 ($tc): $tree" }

# 3) snapshot + mod28: must be 200 and divisible by 28
$snap = "$ApiBase/api/universe/v8/snapshot?format=vertex28&compression=none"
$snapPath = Join-Path $env:TEMP "v8_snapshot.bin"
$sc = Curl-Status $snap $snapPath
if ($sc -ne 200) { throw "snapshot not 200 ($sc): $snap" }
$len = (Get-Item $snapPath).Length
if (($len % 28) -ne 0) { throw "snapshot stride violation: $len bytes" }

# 4) websocket handshake (best-effort)
try {
  $u = [uri]$ApiBase
  $wsScheme = if ($u.Scheme -eq 'https') { 'wss' } else { 'ws' }
  $wsUrl = "${wsScheme}://$($u.Host):$($u.Port)/api/universe/v8/stream"
  $cws = New-Object System.Net.WebSockets.ClientWebSocket
  $cts = New-Object System.Threading.CancellationTokenSource
  $cts.CancelAfter(3000)
  $cws.ConnectAsync([uri]$wsUrl, $cts.Token).GetAwaiter().GetResult() | Out-Null
  if ($cws.State -eq [System.Net.WebSockets.WebSocketState]::Open) { $cws.Abort() }
} catch {
  Write-Host "WS handshake skipped/failed (non-fatal): $($_.Exception.Message)"
}

Write-Host "ROUTE A VERIFIED"
exit 0

