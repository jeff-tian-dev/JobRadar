# AGENTS.md

## Project overview

Automated job search pipeline running 24/7 on a Mac Studio (M4 Max, 32GB). Monitors RSS/Atom feeds from Greenhouse, Lever, Ashby, and Workable ATS platforms, discovers new companies automatically via YC, HN, and GitHub, scores each listing with a local LLM via ollama, stores ranked results in SQLite, serves a Streamlit dashboard, and sends push alerts for high-scoring matches. Zero API costs — everything runs locally.

Two loops:
- **Feed monitor** (`feeds/`) — runs every 3 hours, fetches active RSS feeds → dedup → score → alert
- **Discovery bot** (`discovery/`) — runs daily, finds new companies → resolves their ATS feed URLs → adds to DB

## Tech stack

- **Language**: Python 3.12
- **Feed fetching**: httpx (async HTTP), feedparser (RSS/Atom XML parsing)
- **LLM inference**: ollama with qwen3:14b, accessed via the `ollama` Python package
- **Database**: SQLite (single file at `db/jobs.db`)
- **Dashboard**: Streamlit
- **Alerting**: ntfy.sh (HTTP POST), Slack incoming webhooks, smtplib
- **Scheduling**: macOS launchd (not cron)
- **Config format**: YAML (PyYAML)
- **Testing**: pytest + pytest-asyncio

## Project structure

```
JobRadar/
├── config/
│   ├── settings.example.yaml   # Committed template (no secrets)
│   ├── settings.yaml           # Gitignored — model, db_path, active_profile, per-profile alert secrets
│   ├── seed_companies.yaml     # Manually curated starting companies; processed by discovery/sources/seed.py
│   └── profiles/
│       ├── jeff/profile.yaml   # Scorer-facing profile (skills, preferences, weights, alert_threshold)
│       └── example/profile.yaml
├── feeds/
│   ├── monitor.py              # Fetches all active RSS feeds → list[RawListing]
│   ├── resolver.py             # Given company slug, detects ATS platform, verifies feed URL
│   └── parser.py               # Parses RSS/Atom XML into FeedEntry objects
├── discovery/
│   ├── runner.py               # Orchestrates all discovery sources
│   ├── relevance.py            # LLM-based company relevance pre-filter
│   └── sources/
│       ├── seed.py             # Processes config/seed_companies.yaml
│       ├── hn_hiring.py        # HN "Who's Hiring" thread parser (LLM-assisted)
│       ├── yc.py               # Y Combinator company directory
│       ├── github_trending.py  # GitHub trending orgs
│       └── wellfound.py        # Wellfound/AngelList (currently skipped; requires auth)
├── pipeline/
│   ├── models.py               # RawListing dataclass, fetch_url_with_retry, polite_delay
│   ├── config_paths.py         # Settings load, profile id resolution (CLI > env > settings)
│   ├── db.py                   # SQLite helpers for listings table
│   ├── company_db.py           # SQLite helpers for companies and discovery_runs tables
│   ├── dedup.py                # Hash-based deduplication (title+company+city)
│   ├── normalizer.py           # Parse salaries, locations, dates into structured formats
│   ├── scorer.py               # Calls ollama, parses JSON scores, computes weighted overall
│   └── alerter.py              # Sends ntfy.sh / Slack / email notifications
├── prompts/
│   ├── scoring_system.txt      # System prompt for LLM scorer (do not modify without testing)
│   ├── scoring_user.txt        # User prompt template with {{profile}} and {{listing}} slots
│   ├── hn_parser.txt           # System prompt for parsing HN hiring comments → JSON
│   └── relevance_filter.txt    # System prompt for company relevance pre-filter → JSON
├── dashboard/
│   └── app.py                  # Streamlit app on localhost:8501 (Listings + Companies tabs)
├── db/
│   ├── schema.sql              # listings table schema
│   └── migrations/
│       └── 001_add_companies.sql  # companies, discovery_runs tables; company_id FK on listings
├── scripts/
│   ├── setup.sh                # One-shot install (brew, ollama, pip, db init)
│   ├── bootstrap_all.sh        # Automated full setup
│   ├── run_pipeline.py         # Main entry point — fetch feeds → dedup → score → alert
│   ├── run_discovery.py        # Discovery entry point — find companies → resolve feeds
│   └── install_launchd.sh      # Generates and loads the launchd plists
├── tests/
│   ├── test_scorer.py
│   ├── test_dedup.py
│   ├── test_normalizer.py
│   ├── test_config_paths.py
│   ├── test_company_db.py
│   ├── test_feed_parser.py
│   ├── test_feed_resolver.py
│   ├── test_feed_monitor.py
│   ├── test_discovery.py
│   └── fixtures/               # RSS XML samples, HN comment samples for testing
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Commands

```bash
# One-shot machine setup (brew python@3.12 + ollama, venv, pip, DB, pytest)
bash scripts/bootstrap_all.sh --no-model-pull   # skip large model download
bash scripts/bootstrap_all.sh                   # includes: ollama pull qwen3:14b
bash scripts/bootstrap_all.sh --launchd         # add: install launchd plists

# Discover companies from seed list (first run, before pipeline)
python scripts/run_discovery.py --sources seed --verbose --profile jeff

# Run all discovery sources
python scripts/run_discovery.py --verbose --profile jeff

# Run the feed pipeline once (fetch feeds, dedup, score, alert)
python scripts/run_pipeline.py
python scripts/run_pipeline.py --verbose --profile jeff

# Run tests
pytest tests/ -v

# Start the dashboard
streamlit run dashboard/app.py

# Initialize or reset the database
sqlite3 db/jobs.db < db/schema.sql

# Pull the scoring model (first-time setup)
ollama pull qwen3:14b

# Install the launchd schedules (3h pipeline + daily discovery)
bash scripts/install_launchd.sh
```

## Code style

- Use Python type hints on all function signatures and return types.
- Use dataclasses for structured data (e.g., `RawListing`, `FeedEntry`). No plain dicts for domain objects.
- Async functions for all HTTP/feed fetching code (httpx is async).
- Sync functions for pipeline orchestration, database access, and alerting.
- f-strings for string formatting, not `.format()` or `%`.
- Use `logging` module throughout — never bare `print()` for operational output.
- Docstrings on all public functions (one-line summary, no boilerplate).

```python
# ✅ Good
async def fetch_feed(client: httpx.AsyncClient, company_row: sqlite3.Row) -> list[RawListing]:
    """Fetch and parse one company's RSS feed into RawListing objects."""
    ...

# ❌ Bad
def fetch(row, client):
    print("fetching...")
    ...
```

## Error handling pattern

Every component must be independently failure-tolerant. One broken feed or one unparseable listing must never crash the pipeline.

```python
# ✅ Good — isolate failures, log, continue
for company in companies:
    try:
        listings = await fetch_feed(client, company)
    except Exception:
        logger.exception("Feed fetch failed: %s", company["name"])
        continue

# ❌ Bad — one failure kills everything
all_listings = [await fetch_feed(client, c) for c in companies]
```

## LLM scoring conventions

- Call ollama with `format="json"` and `temperature=0.1`.
- Timeout: 30 seconds per listing. On timeout, log and skip.
- If JSON parsing fails, retry once. If it fails again, log the raw response and skip.
- The three scores (fit, pref, comp) are integers 0–100. Validate this before storing.
- Weighted overall score is computed in Python, not by the LLM: `overall = w1*fit + w2*pref + w3*comp`.
- Scoring weights are read from the active `config/profiles/<id>/profile.yaml` (defaults: 0.40 / 0.35 / 0.25).
- Never hardcode the model name — read it from `config/settings.yaml`.

## Database conventions

- Use parameterized queries everywhere. Never interpolate values into SQL strings.
- Wrap batch inserts in a transaction.
- The `hash` column in `listings` is the dedup key — always check for existence before inserting.
- The `feed_url` column in `companies` is the uniqueness key for companies.
- Status lifecycle for listings: `new` → `reviewing` → `applied` | `rejected` | `expired`.
- Status lifecycle for feeds: `pending` → `active` | `broken` | `no_feed`.

## Testing conventions

- Test files mirror source files: `feeds/parser.py` → `tests/test_feed_parser.py`.
- Use sample RSS XML in `tests/fixtures/` — never hit real websites in tests.
- Mock httpx responses and ollama responses in all tests — no real HTTP or LLM calls.
- For async tests, pytest-asyncio is configured with `asyncio_mode = "auto"` in pyproject.toml.
- Scorer tests: assert valid JSON output, scores are ints 0–100, overall calculation is correct.
- Dedup tests: identical listings produce same hash, minor variations (casing, whitespace) also match.

## Boundaries

- ✅ **Always**: Run `pytest tests/ -v` after changes and confirm all tests pass before considering work complete. Read the active `config/profiles/<id>/profile.yaml` for user preferences — never hardcode skills, salaries, or deal-breakers.
- ⚠️ **Ask first**: Before changing the SQLite schema, the LLM scoring prompts in `prompts/`, or the launchd plist schedule.
- 🚫 **Never**: Store credentials in code — all secrets (Slack webhook URLs, SMTP passwords, ntfy topic names) go in `config/settings.yaml` which is gitignored. Never modify profile YAML programmatically — profiles under `config/profiles/` are user-edited only. Never remove a test because it is failing.
