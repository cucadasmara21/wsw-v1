# Development & Quick Start

## One-command quick start

- Linux / Codespaces:

```bash
./scripts/dev.sh
```

- Windows (PowerShell):

```powershell
./scripts/dev.ps1
```

These scripts will create/activate a `.venv`, install minimal backend dependencies, init the DB and start both backend (8000) and frontend (5173) dev servers. The scripts perform quick health checks: they call `GET /health` on the backend and request the frontend root to check it's serving HTML. If the preferred frontend port (5173) is busy, the script will choose an available ephemeral port and report the final URL to open.

## Recovering from stuck ports & common fixes

- On Linux / Codespaces:
  - Find process using a port: `lsof -n -i :8000` or `ss -ltn 'sport = :8000'`
  - Kill it: `lsof -t -i :8000 | xargs -r kill -9` or `fuser -k 8000/tcp`
  - Use our helper (dry-run): `./scripts/doctor.sh` or to kill: `./scripts/kill-ports.sh --yes`

- On Windows (PowerShell):
  - Find: `Get-NetTCPConnection -LocalPort 8000 | Select-Object -ExpandProperty OwningProcess`
  - Kill: `Stop-Process -Id <pid> -Force` or use `./scripts/kill-ports.ps1 -Yes`

- Vite uses strictPort=true to avoid silent port switching. If 5173 is busy, the devserver will fail early.

- If a `git rebase` hangs waiting for an editor: either set `GIT_EDITOR=true git rebase --continue` (non-interactive) or `export GIT_EDITOR="code --wait"`.

- VSCode multi-line paste warning: it's a security feature — approve if you trust the source or paste in smaller chunks.

## Smoke test commands

Open 3 terminals:

T1 (backend):
```
# create venv if needed
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python init_db.py
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

T2 (frontend):
```
cd frontend
npm ci
npm run dev -- --host 0.0.0.0 --port 5173
```

T3 (verify):
```
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/version
npm --prefix frontend run build
pytest -q
```
