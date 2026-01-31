param(
  [switch]$Yes
)

Set-StrictMode -Version Latest

function Kill-Port($port){
  $conns = $null
  try {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
  } catch {
    Write-Output "Get-NetTCPConnection not available"
    return
  }

  if (-not $conns) {
    Write-Output "No process listening on $port"
    return
  }

  $pids = $conns.OwningProcess | Sort-Object -Unique
  Write-Output "Would kill PIDs on port ${port}: $($pids -join ', ')"
  if ($Yes) {
    foreach ($procId in $pids) {
      try { Stop-Process -Id $procId -Force -ErrorAction Stop }
      catch { Write-Output "Failed to kill PID $procId on port ${port}: $($_.Exception.Message)" }
    }
  }
}

Kill-Port 8000
Kill-Port 5173

if (-not $Yes) { Write-Output "Run with -Yes to actually kill the processes (destructive)." }