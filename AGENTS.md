# AGENTS.md

## Project overview

Automated job search pipeline running 24/7 on a Mac Studio (M4 Max, 32GB). Scrapes listings from LinkedIn, Indeed, Glassdoor, and career pages on a schedule, scores each one with a local LLM via ollama, stores ranked results in SQLite, serves a Streamlit dashboard, and sends push alerts for high-scoring matches. Zero API costs — everything runs locally.

## Tech stack

- **Language**: Python 3.12
- **Scraping**: playwright (async, for JS-heavy sites), httpx + selectolax (static pages)
- **LLM inference**: ollama with qwen2.5:14b-instruct-q4_K_M, accessed via the `ollama` Python package
- **Database**: SQLite (single file at `db/jobs.db`)
- **Dashboard**: Streamlit
- **Alerting**: ntfy.sh (HTTP POST), Slack incoming webhooks, smtplib
- **Scheduling**: macOS launchd (not cron)
- **Config format**: YAML (PyYAML)
- **Testing**: pytest

## Project structure

```
job-search-agent/
├── config/
│   ├── profile.yaml          # User resume, skills, preferences, deal-breakers, scoring weights
│   ├── sources.yaml          # Scraper targets, search queries, CSS selectors
│   └── settings.yaml         # Alert thresholds, model name, scheduling intervals
├── scrapers/
│   ├── base.py               # Abstract base scraper (rate limiting, retry, UA rotation)
│   ├── linkedin.py
│   ├── indeed.py
│   ├── glassdoor.py
│   └── career_pages.py       # Generic scraper driven by sources.yaml selectors
├── pipeline/
│   ├── dedup.py              # Hash-based deduplication (title+company+location)
│   ├── normalizer.py         # Parse salaries, locations, dates into structured formats
│   ├── scorer.py             # Calls ollama, parses JSON scores, computes weighted overall
│   └── alerter.py            # Sends ntfy.sh / Slack / email notifications
├── prompts/
│   ├── scoring_system.txt    # System prompt for LLM scorer (do not modify without testing)
│   └── scoring_user.txt      # User prompt template with {{profile}} and {{listing}} slots
├── dashboard/
│   └── app.py                # Streamlit app on localhost:8501
├── db/
│   ├── schema.sql            # SQLite schema definition
│   └── migrations/
├── scripts/
│   ├── setup.sh              # One-shot install (brew, ollama, pip, playwright, db init)
│   ├── run_pipeline.py       # Main entry point — scrape → dedup → score → alert
│   └── install_launchd.sh    # Generates and loads the launchd plist
├── tests/
│   ├── test_scorer.py
│   ├── test_dedup.py
│   └── fixtures/             # Sample job listings as JSON for testing
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Commands

```bash
# Run the full pipeline once (scrape, dedup, score, alert)
python scripts/run_pipeline.py

# Run with verbose logging
python scripts/run_pipeline.py --verbose

# Run tests
pytest tests/ -v

# Start the dashboard
streamlit run dashboard/app.py

# Initialize or reset the database
sqlite3 db/jobs.db < db/schema.sql

# Pull the scoring model (first-time setup)
ollama pull qwen2.5:14b-instruct-q4_K_M

# Install playwright browsers
playwright install chromium

# Install the launchd schedule
bash scripts/install_launchd.sh
```

## Code style

- Use Python type hints on all function signatures and return types.
- Use dataclasses for structured data (e.g., `RawListing`, `ScoredListing`). No plain dicts for domain objects.
- Async functions for all scraping code (playwright and httpx are both async-capable).
- Sync functions for pipeline orchestration, database access, and alerting.
- f-strings for string formatting, not `.format()` or `%`.
- Use `logging` module throughout — never bare `print()` for operational output.
- Docstrings on all public functions (one-line summary, no boilerplate).

```python
# ✅ Good
async def scrape_listings(query: str, max_pages: int = 3) -> list[RawListing]:
    """Scrape job listings matching the query, up to max_pages of results."""
    ...

# ❌ Bad
def scrape(q, n=3):
    print("scraping...")
    ...
```

## Error handling pattern

Every component must be independently failure-tolerant. One broken scraper or one unparseable listing must never crash the pipeline.

```python
# ✅ Good — isolate failures, log, continue
for source in sources:
    try:
        listings = await source.scrape()
    except Exception:
        logger.exception(f"Scraper failed: {source.name}")
        continue

# ❌ Bad — one failure kills everything
listings = await linkedin.scrape() + await indeed.scrape()
```

## LLM scoring conventions

- Call ollama with `format="json"` and `temperature=0.1`.
- Timeout: 30 seconds per listing. On timeout, log and skip.
- If JSON parsing fails, retry once. If it fails again, log the raw response and skip.
- The three scores (fit, pref, comp) are integers 0–100. Validate this before storing.
- Weighted overall score is computed in Python, not by the LLM: `overall = w1*fit + w2*pref + w3*comp`.
- Scoring weights are read from `config/profile.yaml` (defaults: 0.40 / 0.35 / 0.25).
- Never hardcode the model name — read it from `config/settings.yaml`.

## Database conventions

- Use parameterized queries everywhere. Never interpolate values into SQL strings.
- Wrap batch inserts in a transaction.
- The `hash` column in `listings` is the dedup key — always check for existence before inserting.
- Status lifecycle: `new` → `reviewing` → `applied` | `rejected` | `expired`.

## Testing conventions

- Test files mirror source files: `scrapers/base.py` → `tests/test_base_scraper.py`.
- Use sample listings in `tests/fixtures/` (JSON) — never hit real websites in tests.
- Scorer tests: assert valid JSON output, scores are ints 0–100, overall calculation is correct.
- Dedup tests: identical listings produce same hash, minor variations (casing, whitespace) also match.
- Mock ollama responses in scorer tests — don't require a running ollama instance for CI.

## Boundaries

- ✅ **Always**: Run `pytest tests/ -v` after changes and confirm all tests pass before considering work complete. Read `config/profile.yaml` for user preferences — never hardcode skills, salaries, or deal-breakers.
- ⚠️ **Ask first**: Before changing the SQLite schema, the LLM scoring prompts in `prompts/`, or the launchd plist schedule.
- 🚫 **Never**: Store credentials in code — all secrets (Slack webhook URLs, SMTP passwords, ntfy topic names) go in `config/settings.yaml` which is gitignored. Never modify `config/profile.yaml` programmatically — it is user-edited only. Never remove a test because it is failing.
