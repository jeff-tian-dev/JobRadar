# JobRadar

Local job search pipeline: scrape listings, score with **ollama**, store in **SQLite**, review in a **React + FastAPI** dashboard, alerts via **ntfy** / Slack / SMTP.

## Quick start

**All-in-one (commands only):**

```bash
cd /path/to/JobRadar
bash scripts/bootstrap_all.sh --no-model-pull   # fast: brew, venv, pip, playwright, DB, pytest
# Later (large download): brew services start ollama && ollama pull qwen3:14b
bash scripts/bootstrap_all.sh                   # same as above but waits for full model pull
bash scripts/bootstrap_all.sh --launchd         # append: install launchd plist
```

Then edit `config/settings.yaml` for `profiles.jeff.ntfy_topic` and any Slack/SMTP secrets (no command can guess these).

**Step-by-step alternative:**

1. `bash scripts/setup.sh` (Homebrew, venv, deps, Playwright Chromium, DB init).
2. Copy and edit `config/settings.yaml` (from `settings.example.yaml` if needed).
3. Tune `config/profiles/jeff/profile.yaml` and `config/sources.yaml`.
4. `source .venv/bin/activate` then `python scripts/run_pipeline.py --verbose`
5. `bash scripts/dev.sh` — opens the UI at **http://localhost:5173** (API on **http://localhost:8000**). For a static production build: `cd dashboard/frontend && npm ci && npm run build`, then `uvicorn dashboard.api:app --port 8000` and open **http://localhost:8000**.

Scheduling: `bash scripts/install_launchd.sh` (3-hour interval; override `JOB_SEARCH_PROFILE` before running the script if needed).

See **[docs/handbook.md](docs/handbook.md)** for full usage (run, adjust, modify, upgrades), **[docs/remote-access.md](docs/remote-access.md)** to use the dashboard from another computer via SSH tunnel, **[docs/](docs/README.md)** for all docs, [AGENTS.md](AGENTS.md) for conventions, and [job-search-agent-prompt.md](job-search-agent-prompt.md) for the original spec.
