# PowerShell dev script for Windows
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Root/..

$PORT = 8000
$VITE_PORT = 5173

function Test-PortBusy($port) {
    try {
        $c = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if ($null -ne $c) { Write-Output "⚠️ Port $port appears in use: $($c.OwningProcess)" }
    } catch { }
}

Test-PortBusy $PORT
Test-PortBusy $VITE_PORT

Write-Output "Creating virtualenv .venv (try py -3.12 then python)..."
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.12 -m venv .venv
} else {
    python -m venv .venv
}

# Activate the venv
. .\.venv\Scripts\Activate.ps1

Write-Output "Upgrading pip and installing requirements..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

Write-Output "Initializing database..."
python init_db.py

Write-Output "Starting backend on http://127.0.0.1:$PORT"
Start-Process -NoNewWindow -FilePath python -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port $PORT --reload"
Start-Sleep -Seconds 1

Write-Output "Starting frontend on http://0.0.0.0:$VITE_PORT (strictPort=true)"
Push-Location frontend
npm ci
Start-Process -NoNewWindow -FilePath npm -ArgumentList "run dev -- --host 0.0.0.0 --port $VITE_PORT --strictPort"
Pop-Location

Write-Output "Dev environment started. Use Stop-Process -Id <pid> to stop processes or run scripts/doctor.ps1 for guidance."