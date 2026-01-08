#!/usr/bin/env bash
set -euo pipefail

echo "Creating virtualenv .venv (Python 3.x)..."
python -m venv .venv

# Activate venv for the remainder of the script
# shellcheck source=/dev/null
. .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo "Initializing database..."
python init_db.py

echo "Starting uvicorn on 0.0.0.0:8000 (reload enabled)"
exec python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
