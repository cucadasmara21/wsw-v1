Set-StrictMode -Version Latest
param(
  [switch]$Yes
)

function Kill-Port($port){
  try{
    $conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
    if ($conns) {
      $pids = $conns.OwningProcess | Sort-Object -Unique
      Write-Output "Would kill PIDs on port $port: $($pids -join ', ')"
      if ($Yes) {
        foreach ($pid in $pids) { Stop-Process -Id $pid -Force }
      }
    } else { Write-Output "No process listening on $port" }
  } catch { Write-Output "Get-NetTCPConnection not available" }
}

Kill-Port 8000
Kill-Port 5173

if (-not $Yes) { Write-Output "Run with -Yes to actually kill the processes (destructive)." }