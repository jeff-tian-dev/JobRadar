# JobRadar

> **Automated job-search pipeline that runs 24/7 on your Mac — zero API costs, everything local.**

JobRadar monitors RSS/Atom feeds from Greenhouse, Lever, Ashby, and Workable, discovers new companies automatically via YC, Hacker News hiring threads, and GitHub Trending (each source toggled in `config/settings.yaml`), scores each listing against your personal profile using a **local LLM (qwen3:14b via Ollama)**, stores ranked results in SQLite, and surfaces them through a **React + FastAPI dashboard**. High-scoring matches trigger push alerts (ntfy.sh, Slack, or email). The dashboard can **tailor a résumé** to a job description from `experience-dossier.md` and `profile.yaml`, emitting an **ATS-style PDF** via HTML and **Playwright** (with optional one-page enforcement). A Word template is optional legacy tooling only—see `config/settings.example.yaml`.

---

## Features

| | |
|---|---|
| **Multi-source discovery** | Seed list, YC directory, HN hiring parser, GitHub Trending, optional Wellfound (off by default; needs auth) — LLM relevance pre-filter before adding companies |
| **ATS feed resolution** | Auto-detects Greenhouse / Lever / Ashby / Workable and verifies live feed URLs |
| **Local LLM scoring** | Three independent scores — skill fit, role preference, company competitiveness — weighted and combined in Python, never in the model |
| **Smart dedup** | Hash-based (title + company + city); skips re-scoring the same hash if scored within the last 7 days |
| **React dashboard** | Filter, sort, update status, re-score listings, JD-based résumé tailoring with in-browser PDF preview and download |
| **Push alerts** | ntfy.sh, Slack webhook, or SMTP email digest — fires only above your configured score threshold |
| **launchd scheduling** | Feed pipeline every 3 hours, discovery daily — no cron, no cloud, no fees |
| **pytest suite** | Full coverage across pipeline, feeds, discovery, scorer, tailor |

---

## Architecture

```
Discovery  (daily via launchd → scripts/run_daily_discovery.sh)
  └─ optional: import_simplify.py merges SimplifyJobs public JSON into seed_companies.yaml
  └─ run_discovery.py: seed + YC / HN / GitHub / … (per settings.yaml)
  └─ LLM relevance filter → probes ATS → resolves live feed URLs
  └─ writes company rows → db/jobs.db

Feed pipeline  (every 3 hours via launchd → run_pipeline.py)
  └─ feeds/: fetch all active RSS/Atom feeds → RawListing objects
  └─ filters: title keywords → seniority exclusion → location → max_listing_age_days
  └─ dedup: skip if same hash scored within 7 days
  └─ pipeline/scorer.py: Ollama (fit / preference / competitiveness)
  └─ alerts when overall score ≥ profile alert_threshold

Dashboard  (dev: Vite :5173 + API :8000; prod: uvicorn serves built SPA on :8000)
  └─ dashboard/api.py + dashboard/frontend → db/jobs.db
  └─ résumé tailor: pipeline/resume_tailor.py + prompts/resume_tailor*.txt
```

---

## Tech stack

- **Runtime**: Python 3.12, macOS launchd
- **LLM**: [Ollama](https://ollama.ai) — `qwen3:14b` (runs entirely on-device)
- **Feed fetching**: `httpx` (async) + `feedparser`
- **Database**: SQLite (`db/jobs.db`)
- **Dashboard API**: FastAPI + Uvicorn
- **Dashboard UI**: React 18, TypeScript, Tailwind CSS, Vite (**Node.js** required for `npm` / `dev.sh`)
- **Résumé / PDF**: Playwright Chromium for tailor PDF export; `pypdf` to count pages for one-page enforcement (see `config/settings.example.yaml`)
- **Alerting**: ntfy.sh, Slack incoming webhooks, `smtplib`
- **Testing**: pytest + pytest-asyncio (118 tests, all passing)

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

# 6. Open the dashboard (install Node.js first, e.g. brew install node)
bash scripts/dev.sh        # dev: Vite :5173 proxies /api → FastAPI :8000
# — or for production —
cd dashboard/frontend && npm ci && npm run build && cd ../..
uvicorn dashboard.api:app --port 8000  # built SPA served from /
```

---

## Repository layout

```text
JobRadar/
├── config/           # settings.example.yaml, seed_companies.yaml, profiles/<id>/
├── feeds/            # RSS monitor, parser, ATS resolver
├── discovery/        # runner, relevance filter, sources (seed, yc, hn_hiring, github, wellfound)
├── pipeline/         # dedup, normalizer, db, scorer, alerter, resume_tailor, pdf helpers
├── dashboard/        # FastAPI api.py; frontend/ (Vite + React)
├── prompts/          # scoring, HN parser, relevance, résumé-tailor templates
├── scripts/          # bootstrap_all, run_pipeline, run_discovery, dev.sh, install_launchd, import_simplify, …
├── db/               # schema.sql, migrations/
└── tests/            # pytest (mocked HTTP / LLM — no network)
```

---

## Configuration

| File | Committed | Purpose |
|---|---|---|
| `config/settings.example.yaml` | Yes | Documented template |
| `config/settings.yaml` | **No** (gitignored) | Real settings: Ollama URL, `db_path`, `active_profile`, alert secrets |
| `config/profiles/<id>/profile.yaml` | Yes | Scoring weights, target titles, locations, deal-breakers |
| `config/seed_companies.yaml` | Yes | Hand-curated company list (~2 500 companies) |

**Optional profile files** (paths overridable in `settings.yaml`): `experience-dossier.md` (required for tailoring), `profile.yaml` (contact, education, certifications), and optionally a Word template for legacy flows—see `config/settings.example.yaml`.

All secrets (ntfy topic, Slack webhook URL, SMTP password) live exclusively in `config/settings.yaml` — never committed.

---

## Scheduling

```bash
bash scripts/install_launchd.sh
```

Installs two launchd jobs:

| Job | Interval | Command |
|---|---|---|
| Feed pipeline | Every 3 hours | `run_pipeline.py` |
| Discovery | Daily | `run_daily_discovery.sh` (runs `import_simplify.py` then `run_discovery.py` with sources enabled in settings) |

To run discovery alone (no SimplifyJobs import): `python scripts/run_discovery.py --verbose --profile jeff`.

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
