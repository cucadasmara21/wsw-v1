Set-StrictMode -Version Latest

Write-Output "=== Environment ==="
python --version 2>$null
node --version 2>$null
npm --version 2>$null

function Check-Port($port){
    Write-Output "\nChecking port $port..."
    try {
        $c = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($null -ne $c) { $c | Format-Table -AutoSize }
        else { Write-Output "No listener on $port" }
    } catch { Write-Output "Get-NetTCPConnection not available" }
}

Check-Port 8000
Check-Port 5173

Write-Output "\nIf a port is listed above, note the PID and use scripts/kill-ports.ps1 to terminate or use Task Manager / Stop-Process."