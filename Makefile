# Makefile - developer conveniences
.PHONY: dev doctor install ci

# Start both backend and frontend dev env (uses scripts/dev.sh)
dev:
	./scripts/dev.sh

# Run local checks
doctor:
	./scripts/doctor.sh

# Install backend and frontend dependencies
install:
	python -m venv .venv || true
	. .venv/bin/activate && python -m pip install -U pip && pip install -r requirements.txt
	npm ci --no-audit --no-fund || true
	cd frontend && npm ci --no-audit --no-fund

# Quick CI-like check (local)
ci:
	pytest -q || true
	(cd frontend && npm ci && npm run build)
