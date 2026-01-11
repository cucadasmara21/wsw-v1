#!/usr/bin/env bash
set -e

echo "🧪 Backend Test Suite"
echo "===================="

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest not found. Installing test dependencies..."
    pip install -q -r requirements-dev.txt
fi

echo ""
echo "Running pytest..."
python -m pytest -v --tb=short

echo ""
echo "✅ Backend tests passed!"
