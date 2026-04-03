#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew not found. Install from https://brew.sh then re-run."
  exit 1
fi

brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
command -v ollama >/dev/null 2>&1 || brew install ollama

python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

if [[ ! -f "$ROOT/config/settings.yaml" ]]; then
  cp "$ROOT/config/settings.example.yaml" "$ROOT/config/settings.yaml"
  echo "Created config/settings.yaml from example — add ntfy topic / secrets as needed."
fi

mkdir -p "$ROOT/db"
sqlite3 "$ROOT/db/jobs.db" < "$ROOT/db/schema.sql" || true
echo "DB ready at db/jobs.db"

if command -v ollama >/dev/null 2>&1; then
  ollama pull qwen3:14b || echo "Could not pull model (start ollama and retry: ollama pull ...)"
fi

echo "Done. Edit config/profiles/jeff/profile.yaml and config/seed_companies.yaml as needed."
echo "Optional: bash scripts/install_launchd.sh"
