#!/usr/bin/env bash
set -euo pipefail

# Dev helper for Codespaces / Linux / Mac
# Starts backend (uvicorn) on PORT 8000 and frontend (vite) on 5173

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "🚀 WallStreetWar Dev Environment - Linux/macOS"
echo ""

# Check Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "❌ Python not found. Install Python 3.10+ and try again."
    exit 1
fi

PYTHON_CMD=$(command -v python3 || command -v python)
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo "✅ Python: $PYTHON_VERSION"

# Check Node
if ! command -v node &>/dev/null; then
    echo "❌ Node.js not found. Install Node.js 18+ and try again."
    exit 1
fi

NODE_VERSION=$(node --version)
echo "✅ Node.js: $NODE_VERSION"
echo ""

# Port configuration
: ${PORT:=8000}
VITE_PORT=5173

# Check if ports are busy
warn_if_busy() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
      echo "❌ Port $port is busy. Kill the process using:"
      echo "   lsof -ti:$port | xargs kill -9"
      exit 1
    fi
  elif command -v lsof >/dev/null 2>&1; then
    if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
      echo "❌ Port $port is busy. Kill the process using:"
      echo "   lsof -ti:$port | xargs kill -9"
      exit 1
    fi
  fi
}

warn_if_busy "$PORT"
warn_if_busy "$VITE_PORT"

# Check .env file
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found."
    if [ -f ".env.example" ]; then
        echo "Creating .env from .env.example..."
        cp .env.example .env
        echo "✅ Created .env from .env.example"
        echo "   Review .env and adjust settings if needed."
    else
        echo "❌ .env.example not found. Create .env manually."
        exit 1
    fi
fi

echo ""
echo "📦 Setting up Python environment..."

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv .venv
fi

# Activate venv
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
python -m pip install --upgrade pip --quiet

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt --quiet

# Initialize database
echo ""
echo "🗄️  Initializing database..."
python init_db.py

echo ""
echo "📦 Setting up frontend..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "Installing npm dependencies..."
    npm ci --silent
else
    echo "✅ node_modules already installed"
fi
cd ..

echo ""
echo "🚀 Starting services..."
echo "   Backend:  http://localhost:$PORT"
echo "   Frontend: http://localhost:$VITE_PORT"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Start backend in background
echo "Starting backend on http://127.0.0.1:$PORT"
python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" --reload &
UV_PID=$!

# Wait a bit for backend to start
sleep 3

# Start frontend in background
echo "Starting frontend on http://127.0.0.1:$VITE_PORT"
(cd frontend && npm run dev -- --host 127.0.0.1 --port $VITE_PORT) &
VITE_PID=$!

# Ensure processes are cleaned up on exit
trap 'echo ""; echo "🛑 Stopping services..."; kill ${VITE_PID:-} ${UV_PID:-} 2>/dev/null || true; echo "✅ All services stopped"; exit' EXIT INT TERM

# Wait and check health
sleep 3

echo ""
echo "Checking backend health..."
if curl -sS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "✅ Backend health check passed"
else
  echo "⚠️  Backend health check failed. Check logs above."
fi

echo ""
echo "================================"
echo "🎉 Development environment ready!"
echo "================================"
echo ""
echo "Open in browser:"
echo "  Frontend: http://localhost:$VITE_PORT"
echo "  Backend:  http://localhost:$PORT/docs"
echo "  Health:   http://localhost:$PORT/health"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Wait indefinitely
wait