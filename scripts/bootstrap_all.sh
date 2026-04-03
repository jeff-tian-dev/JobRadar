#!/usr/bin/env bash
# Automates local setup that can be done from the shell (brew, venv, deps, DB, tests, ollama).
#
# Usage:
#   bash scripts/bootstrap_all.sh                  # full setup + ollama pull (large download, long)
#   bash scripts/bootstrap_all.sh --no-model-pull  # skip model download; finish in minutes
#   bash scripts/bootstrap_all.sh --launchd        # also install launchd job (add to any run above)
#
# You still must edit config/settings.yaml for secrets (ntfy topic, Slack, SMTP).
# Compliance / ToS: your responsibility.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:$PATH"
export PATH

INSTALL_LAUNCHD=false
NO_MODEL_PULL=false
for arg in "$@"; do
  case "$arg" in
    --launchd) INSTALL_LAUNCHD=true ;;
    --no-model-pull) NO_MODEL_PULL=true ;;
  esac
done

if ! command -v brew >/dev/null 2>&1; then
  echo "Install Homebrew first: https://brew.sh"
  exit 1
fi

echo "==> brew: python@3.12, ollama (if missing)"
brew list python@3.12 >/dev/null 2>&1 || brew install python@3.12
brew list ollama >/dev/null 2>&1 || brew install ollama

echo "==> LibreOffice (optional: dashboard 'Download PDF' for tailored resumes)"
if command -v soffice >/dev/null 2>&1 || [[ -x "/Applications/LibreOffice.app/Contents/MacOS/soffice" ]]; then
  echo "    soffice already available."
else
  echo "    Not found — install with: brew install --cask libreoffice"
fi

PY312="$(brew --prefix python@3.12)/bin/python3.12"
if [[ ! -x "$PY312" ]]; then
  echo "python@3.12 not found at $PY312"
  exit 1
fi

echo "==> venv: $ROOT/.venv"
rm -rf .venv
"$PY312" -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

echo "==> config/settings.yaml"
if [[ ! -f "$ROOT/config/settings.yaml" ]]; then
  cp "$ROOT/config/settings.example.yaml" "$ROOT/config/settings.yaml"
  echo "Created config/settings.yaml — set profiles.jeff.ntfy_topic (and other secrets)."
else
  echo "config/settings.yaml exists; not overwriting."
fi

echo "==> SQLite"
mkdir -p "$ROOT/db"
sqlite3 "$ROOT/db/jobs.db" < "$ROOT/db/schema.sql"
echo "DB: $ROOT/db/jobs.db"

echo "==> pytest"
pytest tests/ -q

if $NO_MODEL_PULL; then
  echo "==> Skipped ollama pull (--no-model-pull)."
  echo "    When ready: brew services start ollama"
  echo "    Then: ollama pull qwen3:14b"
else
  echo "==> ollama: start service + pull model (this can take many minutes)"
  brew services start ollama 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "Ollama API not up yet. Run: brew services start ollama"
    echo "Then: ollama pull qwen3:14b"
  else
    ollama pull qwen3:14b
  fi
fi

if $INSTALL_LAUNCHD; then
  echo "==> launchd"
  bash "$ROOT/scripts/install_launchd.sh"
else
  echo "==> launchd skipped (pass --launchd to install)."
fi

echo ""
echo "Done."
echo "  Edit secrets: config/settings.yaml"
echo "  Run pipeline: source .venv/bin/activate && python scripts/run_pipeline.py --verbose --profile jeff"
echo "  Dashboard:    bash scripts/dev.sh   # FastAPI :8000 + Vite :5173 → http://localhost:5173"
