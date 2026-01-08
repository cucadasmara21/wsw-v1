# PowerShell dev script for Windows
Set-StrictMode -Version Latest

Write-Output "Creating virtualenv .venv (Python 3.x)..."
python -m venv .venv

# Activate the venv
. .\.venv\Scripts\Activate.ps1

Write-Output "Upgrading pip and installing requirements..."
python -m pip install --upgrade pip
pip install -r requirements.txt

Write-Output "Initializing database..."
python init_db.py

Write-Output "Starting uvicorn on 0.0.0.0:8000"
uvicorn main:app --host 0.0.0.0 --port 8000
