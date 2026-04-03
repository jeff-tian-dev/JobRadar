# JobRadar

> **Automated job-search pipeline that runs 24/7 on your Mac — zero API costs, everything local.**

JobRadar monitors RSS/Atom feeds from Greenhouse, Lever, Ashby, and Workable, discovers new companies automatically via YC, Hacker News Hiring threads, and GitHub Trending, scores each listing against your personal profile using a **local LLM (qwen3:14b via Ollama)**, stores ranked results in SQLite, and surfaces them through a **React + FastAPI dashboard**. High-scoring matches trigger instant push alerts (ntfy.sh, Slack, or email).

---

## Features

| | |
|---|---|
| **Multi-source discovery** | Seed list, Y Combinator directory, HN "Who's Hiring" threads, GitHub Trending orgs |
| **ATS feed resolution** | Auto-detects Greenhouse / Lever / Ashby / Workable and verifies live feed URLs |
| **Local LLM scoring** | Three independent scores — skill fit, role preference, company competitiveness — weighted and combined in Python, never in the model |
| **Smart dedup** | Hash-based (title + company + city) — won't re-score listings you've already seen |
| **React dashboard** | Filter, sort, update status, re-score individual listings, tailor your résumé to a JD with one click |
| **Push alerts** | ntfy.sh, Slack webhook, or SMTP email digest — fires only above your configured score threshold |
| **launchd scheduling** | Feed pipeline every 3 hours, discovery daily — no cron, no cloud, no fees |
| **109-test suite** | Full pytest coverage across every pipeline module |

---

## Architecture

```
Discovery  (runs daily via launchd)
  └─ seed_companies.yaml + YC / HN / GitHub sources
  └─ probes ATS platforms → resolves live feed URLs
  └─ writes company rows → db/jobs.db

Feed pipeline  (runs every 3 hours via launchd)
  └─ fetches all active RSS/Atom feeds → RawListing objects
  └─ filters: title keywords → seniority exclusion → location → age
  └─ dedup: skip if already scored within 7 days
  └─ scores each listing with Ollama (fit / preference / competitiveness)
  └─ alerts when overall score ≥ threshold

Dashboard  (localhost:8000 / tunnel for remote access)
  └─ React SPA + FastAPI backend reading db/jobs.db
  └─ tailor résumé to any listing via local LLM
```

---

## Tech stack

- **Runtime**: Python 3.12, macOS launchd
- **LLM**: [Ollama](https://ollama.ai) — `qwen3:14b` (runs entirely on-device)
- **Feed fetching**: `httpx` (async) + `feedparser`
- **Database**: SQLite (`db/jobs.db`)
- **Dashboard API**: FastAPI + Uvicorn
- **Dashboard UI**: React 18, TypeScript, Tailwind CSS, Vite
- **Alerting**: ntfy.sh, Slack incoming webhooks, `smtplib`
- **Testing**: pytest + pytest-asyncio (109 tests, all passing)

---

## Quick start

### One-command setup

```bash
git clone https://github.com/jeff-tian-dev/JobRadar.git && cd JobRadar

# Install Homebrew deps, Python venv, pip packages, init DB, run tests
bash scripts/bootstrap_all.sh --no-model-pull

# Pull the scoring model (~9 GB, only needed once)
brew services start ollama && ollama pull qwen3:14b

# Optional: install launchd plists for automated scheduling
bash scripts/bootstrap_all.sh --launchd
```

### Step-by-step

```bash
# 1. Install dependencies
bash scripts/setup.sh

# 2. Configure (copy the template, fill in optional alert secrets)
cp config/settings.example.yaml config/settings.yaml
# Edit: ollama_model, db_path, active_profile, ntfy/Slack/SMTP if desired

# 3. Tune your scoring profile
#    config/profiles/jeff/profile.yaml  ← target titles, locations, weights

# 4. Seed the company list (first run)
source .venv/bin/activate
python scripts/run_discovery.py --sources seed yc --profile jeff

# 5. Run the feed pipeline
python scripts/run_pipeline.py --verbose --profile jeff

# 6. Open the dashboard
bash scripts/dev.sh        # dev mode: React on :5173, API on :8000
# — or for production —
cd dashboard/frontend && npm ci && npm run build && cd ../..
uvicorn dashboard.api:app --port 8000  # SPA served from /
```

---

## Configuration

| File | Committed | Purpose |
|---|---|---|
| `config/settings.example.yaml` | Yes | Documented template |
| `config/settings.yaml` | **No** (gitignored) | Real settings: Ollama URL, `db_path`, `active_profile`, alert secrets |
| `config/profiles/<id>/profile.yaml` | Yes | Scoring weights, target titles, locations, deal-breakers |
| `config/seed_companies.yaml` | Yes | Hand-curated company list (~2 500 companies) |

All secrets (ntfy topic, Slack webhook URL, SMTP password) live exclusively in `config/settings.yaml` — never committed.

---

## Scheduling

```bash
bash scripts/install_launchd.sh
```

Installs two launchd plists:

| Agent | Interval |
|---|---|
| Feed pipeline (`run_pipeline.py`) | Every 3 hours |
| Discovery (`run_discovery.py`) | Daily |

---

## Dashboard

Start with `bash scripts/dev.sh` (or via SSH tunnel for remote use — see [docs/remote-access.md](docs/remote-access.md)).

- **Listings tab** — sortable table with scores, status controls, one-click résumé tailoring
- **Companies tab** — manage monitored companies, force feed re-checks, view discovery history

---

## Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

All 109 tests run offline — no real HTTP calls, no Ollama inference.

---

## Documentation

| Doc | Contents |
|---|---|
| [docs/handbook.md](docs/handbook.md) | Full usage guide — running, tuning, upgrading |
| [docs/configuration.md](docs/configuration.md) | YAML field reference |
| [docs/remote-access.md](docs/remote-access.md) | Access the dashboard from another machine via SSH tunnel |
| [docs/project-map.md](docs/project-map.md) | Module map and data-flow diagram |
| [AGENTS.md](AGENTS.md) | Code conventions and contributor guidelines |

---

## License

Personal project. Not licensed for redistribution.
