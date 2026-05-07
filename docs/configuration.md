# Configuration

## Files overview

| File | Committed? | Purpose |
|------|------------|---------|
| `config/settings.example.yaml` | Yes | Safe template without secrets |
| `config/settings.yaml` | **No** (gitignored) | Real settings: Ollama, `db_path`, `active_profile`, per-profile alert secrets |
| `config/seed_companies.yaml` | Yes | Curated companies for discovery source `seed` |
| `config/profiles/<id>/profile.yaml` | Usually yes for your own profile | Resume-shaped data for the **scorer** (skills, preferences, weights, `alert_threshold`) |

## `settings.yaml`

Typical keys:

- **`active_profile`** — default profile id (e.g. `jeff`).
- **`profiles_dir`** — default `config/profiles`.
- **`db_path`** — default `db/jobs.db` (path to SQLite file).
- **`ollama_model`**, **`ollama_host`**, **`ollama_timeout_seconds`** — inference endpoint and model name.
- **`ollama_tailor_temperature`**, **`ollama_tailor_timeout_seconds`**, **`ollama_tailor_num_predict`** (optional) — dashboard resume tailoring; lower temperature (e.g. **0.28**) yields more consistent bullets than high values.
- **`ollama_tailor_think`** (optional, auto-detected) — `true` enables Ollama thinking mode so the model reasons through project scoring before emitting JSON (thinking logged to `pipeline.log`). Default: `true` for `qwen3:*` models, off for all others.
- **`max_listing_age_days`** — default **7**: skip scraped rows whose **posted** date parses and is **strictly older** than this many days (e.g. 8+ days ago when set to 7). Set to **`null`** to disable (unknown/missing posted dates are never skipped by this rule).
- **`profiles.<id>.ntfy_topic`** — ntfy topic name (not the full URL).
- **`profiles.<id>.slack_webhook_url`**, **`smtp_*`** — optional; see example file.

Create the file once:

```bash
cp config/settings.example.yaml config/settings.yaml
```

Then edit **`config/settings.yaml`** only on your machine; never commit it if it contains secrets.

Discovery toggles and caps live under **`discovery`** in `settings.yaml` (`enabled`, `relevance_threshold`, `max_companies_per_source`, `sources.*`); see `config/settings.example.yaml`.

## Profile YAML (`config/profiles/<id>/profile.yaml`)

Used entirely for **LLM scoring** and **alert threshold** (not for scraper queries). Shape follows the spec in `job-search-agent-prompt.md`: `summary`, `skills` tiers, `preferences`, `deal_breakers`, `scoring_weights`, `alert_threshold`.

Human resume YAML (e.g. `Jeff_Tian_Resume.yaml` at repo root) is a **separate** source you can merge from when updating the scorer profile; the pipeline runtime reads **`profile.yaml`** under `profiles/<id>/`, not the resume file.

## Environment variables

| Variable | Used by |
|----------|---------|
| `JOB_SEARCH_PROFILE` | Overrides default profile for `run_pipeline.py` when `--profile` is omitted |
| `JOB_SEARCH_PROFILE_DASHBOARD` | Optional override for dashboard (FastAPI) profile selection |
