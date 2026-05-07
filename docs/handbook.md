# JobRadar handbook

This is the main **how-to** for using, running, tuning, and growing the project. For a compact directory map, see [project-map.md](project-map.md). For YAML field reference, see [configuration.md](configuration.md).

---

## 1. One-time startup checklist

| Check | What "good" looks like |
|-------|------------------------|
| **Ollama installed** | `which ollama` prints a path. `ollama --version` works. |
| **API running** | `curl -s http://127.0.0.1:11434/api/tags` returns JSON. Start with the menu bar app or `brew services start ollama` if not. |
| **Model pulled** | `ollama list` includes `qwen3:14b` (~9 GB). |
| **Settings** | `config/settings.yaml` has `ollama_model: qwen3:14b` and `ollama_host: http://127.0.0.1:11434`. |
| **venv + tests** | `source .venv/bin/activate && pytest tests/ -q` — all pass. |
| **DB tables** | `sqlite3 db/jobs.db ".tables"` shows `listings` and `companies` after first run. |

---

## 2. Mental model

```
Discovery (run once, then weekly)
  └─ reads seed_companies.yaml + YC/HN sources
  └─ probes Greenhouse / Lever / Ashby APIs for each company
  └─ writes active feed URLs → companies table in db/jobs.db

Pipeline (run every 3 hours via launchd)
  └─ fetches all active feeds → raw listings
  └─ filters: title keywords → seniority exclusion → location → age (7d)
  └─ dedup: skip if already scored in last 7 days
  └─ scores survivors with Ollama → writes to listings table
  └─ alerts if score ≥ threshold (ntfy / Slack / email digest)

Dashboard
  └─ reads db/jobs.db
  └─ filter / sort / mark status / re-score individual listings
```

**Key files:**
- `db/jobs.db` — your only database (SQLite, stays on this machine)
- `config/profiles/jeff/profile.yaml` — what the LLM thinks "you" are
- `config/seed_companies.yaml` — hand-curated companies to always monitor
- `config/settings.yaml` — runtime config, secrets, filter tuning

---

## 3. Day-to-day usage

### First run (populate the company list)

```bash
cd /path/to/JobRadar
source .venv/bin/activate

# 1. Seed hand-picked companies + discover all YC companies (~30 seconds)
python scripts/run_discovery.py --sources seed yc --profile jeff

# 2. Fetch all feeds, score, store
python scripts/run_pipeline.py --profile jeff

# 3. Open dashboard (React + FastAPI — see repo README)
bash scripts/dev.sh
# → http://localhost:5173 (API proxied via Vite)
```

### Dashboard from another PC (SSH tunnel)

With `dev.sh` running on the Mac, open a tunnel from the other machine (e.g. Windows PowerShell or Command Prompt), then browse **http://127.0.0.1:5173** on that machine. Leave the SSH session open while you use the UI.

```text
ssh -N -L 5173:127.0.0.1:5173 jefftian@100.112.50.147
```

(`100.112.50.147` is a Tailscale address here; same-LAN IP or hostname work if reachable. General patterns and troubleshooting: [remote-access.md](remote-access.md).)

### Ongoing (automated via launchd after setup)

```bash
# Pipeline runs every 3 hours automatically after:
bash scripts/install_launchd.sh

# Discovery runs daily automatically (re-checks for new companies)
# Both are installed by install_launchd.sh
```

### Manual re-run at any time

```bash
source .venv/bin/activate
python scripts/run_pipeline.py --profile jeff
```

---

## 4. Command reference

| Task | Command |
|------|---------|
| Activate venv | `source .venv/bin/activate` |
| Seed + YC discovery | `python scripts/run_discovery.py --sources seed yc --profile jeff` |
| HN "Who's Hiring" discovery | `python scripts/run_discovery.py --sources hn_hiring --profile jeff` |
| All discovery sources | `python scripts/run_discovery.py --profile jeff` |
| Full pipeline run | `python scripts/run_pipeline.py --profile jeff` |
| Verbose pipeline | `python scripts/run_pipeline.py --verbose --profile jeff` |
| Run tests | `pytest tests/ -v` |
| Dashboard (dev) | `bash scripts/dev.sh` → http://localhost:5173 |
| Dashboard (remote) | SSH tunnel example in §3; full guide [remote-access.md](remote-access.md) |
| Install launchd schedules | `bash scripts/install_launchd.sh` |
| Pipeline logs | `~/Library/Logs/job-search-agent/pipeline.log` |
| Check scheduled jobs | `launchctl list \| grep jobsearch` |
| Reset listings (keep companies) | `sqlite3 db/jobs.db "DELETE FROM listings;"` |

---

## 5. How discovery works

Discovery finds companies and resolves their job feed URLs. It writes to the `companies` table. The pipeline only fetches companies that have `feed_status = 'active'`.

### Sources

| Source | Command flag | What it does |
|--------|-------------|--------------|
| **seed** | `--sources seed` | Hand-curated list in `config/seed_companies.yaml`. Verifies each company's feed URL. |
| **yc** | `--sources yc` | Fetches all ~5,700 YC companies, concurrently probes Greenhouse → Lever → Ashby for each. Finds ~700 companies. Takes ~3 minutes. |
| **hn_hiring** | `--sources hn_hiring` | Parses the latest HN "Who's Hiring" thread with the LLM, extracts companies, resolves their feeds. Good for small startups. |

### Adding a company manually

1. Find its ATS platform. Look at the company's careers URL:
   - `boards.greenhouse.io/slug` or `api.greenhouse.io/v1/boards/slug/jobs` → Greenhouse
   - `jobs.lever.co/slug` → Lever
   - `jobs.ashbyhq.com/slug` → Ashby

2. Verify the slug works in a browser:
   - Greenhouse: `https://api.greenhouse.io/v1/boards/SLUG/jobs`
   - Lever: `https://api.lever.co/v0/postings/SLUG?mode=json`
   - Ashby: `https://api.ashbyhq.com/posting-api/job-board/SLUG`

3. Add to `config/seed_companies.yaml`:
   ```yaml
   - name: Acme Corp
     slug: acme
     platform: greenhouse   # or lever / ashby
     website: https://acme.com
     industry: developer tools
   ```

4. Re-run seed discovery:
   ```bash
   python scripts/run_discovery.py --sources seed --profile jeff
   ```

---

## 6. How filtering works (pipeline)

Listings pass through four sequential filters before being scored. All filters are configurable in `config/settings.yaml`.

| Filter | Default behaviour | Setting to change it |
|--------|------------------|---------------------|
| **Title keywords** | Keep only listings whose title contains engineering/data/ML keywords | `title_keywords: [...]` |
| **Seniority exclusion** | Drop titles containing senior/staff/principal/lead/manager/director | `seniority_exclude: [...]` |
| **Location** | Keep Toronto/Ontario/Canada area + empty location (often remote) | `toronto_terms: [...]` |
| **Age** | Drop listings with a posted date older than 7 days | `max_listing_age_days: 7` (set to `null` to disable) |
| **Dedup** | Skip if already scored within 7 days | hardcoded |

After filtering, survivors are scored by Ollama and written to the DB.

---

## 7. Tuning scoring and alerts

### Profile (`config/profiles/jeff/profile.yaml`)

- **`preferences`** — titles, locations, remote preference, salary floor, industries, deal-breakers. The LLM is instructed to honor deal-breakers strictly.
- **`scoring_weights`** — `fit` / `preference` / `competitiveness` weights (defaults 0.40 / 0.35 / 0.25).
- **`alert_threshold`** — overall score at or above this triggers a push notification (and adds to daily email digest if enabled).

After changing the profile, existing rows keep old scores until re-scored (either by waiting 7 days for the next pipeline pass, or clicking **Re-score** in the dashboard).

### Alerts (`config/settings.yaml`)

```yaml
profiles:
  jeff:
    ntfy_topic: your-topic       # push via ntfy.sh
    slack_webhook_url: https://...
    smtp_to: you@example.com
```

### Resume tailoring (dashboard)

The dashboard **Tailor resume** action fills your Word template from the **experience dossier** plus the job description (Ollama JSON). Steadier bullet length and phrasing:

- Set **`ollama_tailor_temperature`** in `config/settings.yaml` to roughly **0.2–0.35** (the repo default in code and `settings.example.yaml` is **0.28**). Higher values make outputs more random run-to-run.
- **`ollama_tailor_num_predict`** / timeout: see comments in `config/settings.example.yaml` if JSON is truncated.

**Richer dossier → richer bullets:** Under each project in `experience-dossier.md`, flesh out **`### Outcomes`** and **`### What I built / did`** with numbers, scale, and tools the model is allowed to quote. Thin sections produce shorter, more generic lines no matter how strict the prompt is.

---

## 8. Modifying the code

| Area | Location | Notes |
|------|----------|-------|
| Feed parsing | `feeds/parser.py` | Greenhouse JSON, Lever JSON, Ashby JSON, RSS/Atom XML |
| Feed fetching | `feeds/monitor.py` | Async; per-feed try/except; failure counter marks broken after 5 fails |
| Feed resolution | `feeds/resolver.py` | URL patterns, verify_feed_url, try_resolve_feed |
| Discovery sources | `discovery/sources/` | One file per source; each returns count of companies added |
| Pipeline filters | `scripts/run_pipeline.py` | `_title_matches_keywords`, `_is_senior_title`, `_location_ok` |
| Scoring | `pipeline/scorer.py`, `prompts/` | Ollama client, JSON parse, retries, weighted overall |
| DB — listings | `pipeline/db.py`, `db/schema.sql` | Parameterised SQL only |
| DB — companies | `pipeline/company_db.py` | upsert_company, feed status tracking |
| Alerts | `pipeline/alerter.py` | ntfy, Slack, SMTP digest |
| Dashboard | `bash scripts/dev.sh` → `dashboard/api.py` + `dashboard/frontend/` | React + FastAPI; Listings + Companies + résumé tailor |

---

## 9. Troubleshooting

| Symptom | Things to check |
|---------|----------------|
| **Scoring skipped / errors** | Ollama running? `ollama list` has the right model? Logs in `pipeline.log`. |
| **0 listings after pipeline** | Filters too tight? Run `--verbose` to see which filter is dropping everything. Check `max_listing_age_days`. |
| **Feed marked broken** | `SELECT name, feed_status, consecutive_failures FROM companies WHERE feed_status='broken';` — re-activate with dashboard or `UPDATE companies SET feed_status='active', consecutive_failures=0 WHERE name='...';` |
| **Discovery finds 0 companies** | YC API URL changed? Check `discovery/sources/yc.py` `_YC_API_URL`. |
| **No push notifications** | `ntfy_topic` set in settings? Score below `alert_threshold`? Run `--verbose` and look for "maybe_alert" lines. |
| **Dashboard empty** | No successful pipeline run yet, or `db_path` in settings doesn't match where the pipeline wrote. |
| **launchd not firing** | `launchctl list \| grep jobsearch`; check `~/Library/Logs/job-search-agent/`. Re-install with `bash scripts/install_launchd.sh`. |
| **DB locked error** | Another pipeline process is running. `pkill -f run_pipeline` then retry. |

---

## 10. What can be improved

| Idea | Effort | Where |
|------|--------|-------|
| **Slug variant probing** — try `{slug}inc`, `{slug}hq`, etc. to catch more companies | Low | `discovery/sources/yc.py` |
| **Careers page detection** — fetch company website, detect ATS from links | Medium | `feeds/resolver.py` `detect_platform_from_careers_page` (already exists, not wired into YC discovery) |
| **Parallel feed fetching** — reduce 12-min fetch time by fetching multiple feeds concurrently | Low | `feeds/monitor.py` `fetch_all_active_feeds` |
| **Faster/lighter scoring model** | Low | Change `ollama_model` in settings + `ollama pull` |
| **Per-profile location filter** | Low | Move `toronto_terms` into profile YAML |
| **Listing freshness check** | Medium | HTTP HEAD each stored listing URL; mark `expired` if 404 |

---

## 11. Doc index

| Document | Role |
|----------|------|
| **This handbook** | Use, run, adjust, modify, upgrade |
| [project-map.md](project-map.md) | Layout and data-flow diagram |
| [configuration.md](configuration.md) | Config files and env vars reference |
| [../AGENTS.md](../AGENTS.md) | Project overview and contributor rules |
