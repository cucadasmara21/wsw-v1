# Makefile - developer conveniences
.PHONY: dev doctor install ci backend frontend ports

# Start backend in the foreground (open T1)
backend:
	bash ./scripts/run_backend.sh

# Start frontend dev server in the foreground (open T2)
frontend:
	bash ./scripts/run_frontend.sh

# Free ports used by backend/frontend (8000, 5173)
ports:
	bash ./scripts/kill_ports.sh

# Print recommended 3-terminal developer workflow (do NOT use concurrency here)
dev:
	@echo "Developer workflow (use THREE terminals):"
	@echo "  T1: make backend       # runs backend (blocks frontend)"
	@echo "  T2: make frontend      # runs frontend dev server"
	@echo "  T3: make ports && curl http://localhost:8000/health  # free ports and health check"
	@echo ""
	@echo "Note: Open one terminal per process; do not run both backend and frontend in the same shell with concurrency tools."

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
