#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# Install frontend deps if needed
if [ ! -d "dashboard/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd dashboard/frontend && npm install)
fi

# Start FastAPI backend
echo "Starting FastAPI backend on :8000..."
.venv/bin/python -m uvicorn dashboard.api:app --reload --port 8000 &
BACKEND_PID=$!

# Give backend a moment to start
sleep 1

# Start Vite dev server
echo "Starting Vite dev server on :5173..."
(cd dashboard/frontend && npm run dev)

# Cleanup on exit
kill $BACKEND_PID 2>/dev/null || true
