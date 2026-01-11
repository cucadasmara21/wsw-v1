#!/usr/bin/env bash
# System check script for WallStreetWar dev environment

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

echo "🔍 WallStreetWar Environment Check"
echo "=================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

CHECKS_PASSED=0
CHECKS_FAILED=0

check_command() {
    local cmd=$1
    local name=$2
    local min_version=$3
    
    if command -v "$cmd" &>/dev/null; then
        local version=$($cmd --version 2>&1 | head -n 1)
        echo -e "${GREEN}✅${NC} $name: $version"
        ((CHECKS_PASSED++))
    else
        echo -e "${RED}❌${NC} $name not found (expected: $min_version+)"
        ((CHECKS_FAILED++))
    fi
}

# Check Python
echo "1️⃣  Checking Python..."
if command -v python3 &>/dev/null; then
    PYTHON_CMD=python3
elif command -v python &>/dev/null; then
    PYTHON_CMD=python
else
    echo -e "${RED}❌${NC} Python not found"
    ((CHECKS_FAILED++))
    PYTHON_CMD=""
fi

if [ -n "$PYTHON_CMD" ]; then
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
    echo -e "${GREEN}✅${NC} Python: $PYTHON_VERSION"
    ((CHECKS_PASSED++))
    
    # Check if venv exists
    if [ -d ".venv" ]; then
        echo -e "${GREEN}✅${NC} Virtual environment: .venv exists"
        ((CHECKS_PASSED++))
        
        # Check if dependencies are installed
        if [ -f ".venv/bin/activate" ] || [ -f ".venv/Scripts/activate" ]; then
            source .venv/bin/activate 2>/dev/null || source .venv/Scripts/activate 2>/dev/null || true
            if $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
                echo -e "${GREEN}✅${NC} Python dependencies: FastAPI installed"
                ((CHECKS_PASSED++))
            else
                echo -e "${YELLOW}⚠️${NC}  Python dependencies: FastAPI not installed"
                echo "   Run: pip install -r requirements.txt"
                ((CHECKS_FAILED++))
            fi
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  Virtual environment: not created"
        echo "   Run: python3 -m venv .venv"
        ((CHECKS_FAILED++))
    fi
fi

echo ""

# Check Node.js
echo "2️⃣  Checking Node.js..."
check_command "node" "Node.js" "18.0"

if command -v node &>/dev/null; then
    if command -v npm &>/dev/null; then
        NPM_VERSION=$(npm --version)
        echo -e "${GREEN}✅${NC} npm: $NPM_VERSION"
        ((CHECKS_PASSED++))
    else
        echo -e "${RED}❌${NC} npm not found"
        ((CHECKS_FAILED++))
    fi
    
    # Check frontend dependencies
    if [ -d "frontend/node_modules" ]; then
        echo -e "${GREEN}✅${NC} Frontend dependencies: node_modules exists"
        ((CHECKS_PASSED++))
    else
        echo -e "${YELLOW}⚠️${NC}  Frontend dependencies: not installed"
        echo "   Run: cd frontend && npm ci"
        ((CHECKS_FAILED++))
    fi
fi

echo ""

# Check database
echo "3️⃣  Checking Database..."
if [ -f "wsw.db" ]; then
    DB_SIZE=$(du -h wsw.db | cut -f1)
    echo -e "${GREEN}✅${NC} Database: wsw.db exists ($DB_SIZE)"
    ((CHECKS_PASSED++))
else
    echo -e "${YELLOW}⚠️${NC}  Database: wsw.db not found"
    echo "   Run: python init_db.py"
    ((CHECKS_FAILED++))
fi

# Check .env
if [ -f ".env" ]; then
    echo -e "${GREEN}✅${NC} Configuration: .env exists"
    ((CHECKS_PASSED++))
else
    echo -e "${YELLOW}⚠️${NC}  Configuration: .env not found"
    echo "   Run: cp .env.example .env"
    ((CHECKS_FAILED++))
fi

echo ""

# Check ports
echo "4️⃣  Checking Ports..."
PORT=${PORT:-8000}
VITE_PORT=5173

check_port() {
    local port=$1
    local name=$2
    
    if command -v ss >/dev/null 2>&1; then
        if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
            echo -e "${YELLOW}⚠️${NC}  Port $port ($name): BUSY"
            return 1
        fi
    elif command -v lsof >/dev/null 2>&1; then
        if lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            echo -e "${YELLOW}⚠️${NC}  Port $port ($name): BUSY"
            return 1
        fi
    fi
    echo -e "${GREEN}✅${NC} Port $port ($name): available"
    return 0
}

if check_port "$PORT" "backend"; then
    ((CHECKS_PASSED++))
else
    ((CHECKS_FAILED++))
    echo "   Kill process: lsof -ti:$PORT | xargs kill -9"
fi

if check_port "$VITE_PORT" "frontend"; then
    ((CHECKS_PASSED++))
else
    ((CHECKS_FAILED++))
    echo "   Kill process: lsof -ti:$VITE_PORT | xargs kill -9"
fi

echo ""

# Check backend health (if running)
echo "5️⃣  Checking Backend..."
if curl -sS "http://localhost:$PORT/health" >/dev/null 2>&1; then
    HEALTH=$(curl -sS "http://localhost:$PORT/health")
    STATUS=$(echo "$HEALTH" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    echo -e "${GREEN}✅${NC} Backend: running at http://localhost:$PORT"
    echo "   Status: $STATUS"
    ((CHECKS_PASSED++))
else
    echo -e "${YELLOW}⚠️${NC}  Backend: not running"
    echo "   Start with: ./scripts/dev.sh"
fi

echo ""
echo "=================================="
echo "Summary:"
echo -e "${GREEN}✅ Passed: $CHECKS_PASSED${NC}"
if [ $CHECKS_FAILED -gt 0 ]; then
    echo -e "${RED}❌ Failed: $CHECKS_FAILED${NC}"
    echo ""
    echo "Fix the issues above and run this script again."
    exit 1
else
    echo -e "${GREEN}🎉 All checks passed!${NC}"
    echo ""
    echo "Ready to start development:"
    echo "  ./scripts/dev.sh"
    exit 0
fi
