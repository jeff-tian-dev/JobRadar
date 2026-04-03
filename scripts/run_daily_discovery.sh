#!/usr/bin/env bash
# Daily discovery: import new companies from SimplifyJobs, then run full discovery.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
PROFILE="${JOB_SEARCH_PROFILE:-jeff}"

echo "[$(date)] Starting daily discovery"

echo "[$(date)] Importing companies from SimplifyJobs..."
"$PYTHON" "$ROOT/scripts/import_simplify.py"

echo "[$(date)] Running discovery (seed + yc + hn_hiring)..."
"$PYTHON" "$ROOT/scripts/run_discovery.py" --profile "$PROFILE"

echo "[$(date)] Daily discovery complete."
