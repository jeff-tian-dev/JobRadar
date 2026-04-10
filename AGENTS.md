# JobRadar — agent/component map (code-derived)

```
config/settings.yaml + config/profiles/<id>/profile.yaml
  → scripts/run_pipeline.py
      → feeds/monitor.fetch_all_active_feeds → list[RawListing]
      → filters (title_keywords ∧ entry_level_terms ∧ seniority_exclude ∧ toronto_terms ∧ max_listing_age_days)
      → pipeline/dedup.listing_dedup_hash → pipeline/db.upsert_listing_after_scrape
      → pipeline/scorer.score_listing (ollama) → pipeline/db.update_scores
      → pipeline/alerter.maybe_alert_listing + send_daily_email_digest_if_enabled

scripts/run_discovery.py → discovery/runner.run_discovery
  → discovery/sources/{seed,hn_hiring,yc,github,wellfound}.discover_from_*
      → feeds/resolver.try_resolve_feed / verify_feed_url / (YC) FEED_URL_PATTERNS probe
      → pipeline/company_db.upsert_company, insert_discovery_run, finish_discovery_run

dashboard/api.py (FastAPI lifespan)
  → CRUD listings/companies; POST rescore → pipeline/scorer.score_listing
  → POST tailor-* → pipeline/resume_tailor.tailor_resume / rebuild_docx_from_edits
  → POST companies/discover → asyncio.run(discovery/sources/seed.discover_from_seed) only
```

## Entry points
| Path | Callable | Purpose |
| --- | --- | --- |
| scripts/run_pipeline.py | main() | Feed sweep → SQLite listings → score → alerts |
| scripts/run_discovery.py | main() | Multi-source company ingest → companies + discovery_runs |
| dashboard/api.py | app (uvicorn) | REST + static SPA; Ollama for rescore/tailor |

## Data schemas (behavioral)
- **RawListing** (`pipeline/models.py`): source, source_url, title, company, location, description, salary_raw, posted_date, scraped_at, raw_html.
- **Listing DB row** (`pipeline/db.py`): hash dedup; scores fit/pref/comp/overall + reasons; status; optional company_id — `feeds/monitor.fetch_all_active_feeds` never attaches company_id to `RawListing`, so `run_pipeline.raw_to_db_payload` leaves company_id None.
- **ScoreResult** (`pipeline/scorer.py`): fit_score, pref_score, comp_score (0–100 int), reasons, overall_score=float from weighted_overall(profile scoring_weights).
- **TailorPreviewResult** → API dict (`tailor_result_to_api_dict`): filename, docx_base64, original, tailored, explanation, ollama_metrics.
- **ResolvedFeed** (`feeds/resolver.py`): platform, url, status, entry_count.

## LLM call sites
| Function | File | Model | Prompts | Client opts | Output |
| --- | --- | --- | --- | --- | --- |
| score_listing | pipeline/scorer.py | ollama_model | prompts/scoring_system.txt + prompts/scoring_user.txt | host, ollama_timeout_seconds | JSON scores; 1× retry on parse fail |
| _parse_comment_with_llm | discovery/sources/hn_hiring.py | ollama_model | prompts/hn_parser.txt | host only (no Client timeout) | JSON fields or skip |
| call_tailor_llm | pipeline/resume_tailor.py | ollama_tailor_model \|\| ollama_model | prompts/resume_tailor.txt + prompts/resume_tailor_user.txt | ollama_tailor_* | JSON tailor blob |
| call_tailor_fit_one_page_llm | pipeline/resume_tailor.py | same | prompts/resume_tailor_fit_one_page.txt + prompts/resume_tailor_fit_one_page_user.txt | one-page trim loop | JSON trim |
| score_company_relevance | discovery/relevance.py | ollama_model | prompts/relevance_filter.txt | host only | JSON score/reason; used via should_skip_company_for_relevance (hn/yc/github) |

**Ollama options**: temperature 0.1 (scorer/HN/relevance); tailor uses ollama_tailor_temperature; repeat_penalty `read_ollama_repeat_penalty(settings)` (`pipeline/config_paths.py`). **Metrics**: `log_ollama_metrics` / `log_tailor_session_ollama_summary` → `~/Library/Logs/job-search-agent/ollama_metrics.log`.

## HTTP/tools (non-Ollama)
- **feeds/monitor.py**: httpx GET feeds; Greenhouse detail API via `greenhouse_job_detail_api_url`; updates `companies` via `update_feed_success`, `increment_feed_failures`, `update_feed_status` (broken after max_consecutive_failures).
- **hn_hiring**: Algolia `hn.algolia.com`, Firebase `hacker-news.firebaseio.com`.
- **yc.py**: `yc-oss.github.io/api/companies/all.json`; probes greenhouse/lever/ashby URLs from `FEED_URL_PATTERNS`.
- **github_trending.py**: github.com/trending HTML scrape + `api.github.com/orgs/{org}`.
- **wellfound.py**: no HTTP; logs skip, finish_discovery_run completed with error message.
- **alerter.py**: httpx POST ntfy.sh, Slack webhook; smtplib digest.
- **dashboard**: httpx in add_company for `try_resolve_feed`; PDF via `dashboard/pdf_convert.docx_bytes_to_pdf` (LibreOffice); tailor one-page uses `pipeline/pdf_convert` + `pipeline/pdf_pages.count_pdf_pages`.
- **rebuild_docx_from_edits** (`pipeline/resume_tailor.py`): no initial tailor LLM; if `tailor_enforce_one_page` and soffice present, same PDF loop + `call_tailor_fit_one_page_llm` as tailor flow.

## Config keys (consumed in code)
`active_profile`, `profiles_dir`, `db_path`, `ollama_model`, `ollama_host`, `ollama_timeout_seconds`, `ollama_repeat_penalty`, `ollama_tailor_model`, `ollama_tailor_timeout_seconds`, `ollama_tailor_temperature`, `ollama_tailor_num_predict`, `ollama_tailor_num_predict_max`, `ollama_tailor_num_ctx`, `ollama_tailor_think`, `ollama_tailor_fit_one_page_num_predict`, `ollama_tailor_fit_one_page_temperature`, `tailor_enforce_one_page`, `tailor_one_page_max_trim_attempts`, `tailor_pdf_convert_timeout_seconds`, `resume_template_docx`, `resume_docx`, `experience_dossier`, `max_listing_age_days`, `title_keywords`, `entry_level_terms`, `toronto_terms`, `seniority_exclude`, `feeds.fetch_timeout_seconds`, `feeds.max_consecutive_failures`, `discovery.enabled`, `discovery.relevance_threshold`, `discovery.max_companies_per_source`, `discovery.sources.{seed,hn_hiring,yc,github,wellfound}` (plus legacy `github_trending` → github), `discovery.yc_concurrency`, `profiles.<id>.{ntfy_topic,slack_webhook_url,smtp_*}`. **Profile YAML** (`load_profile_for_scoring`): scoring_weights, alert_threshold, plus tailor reads `name` via `load_full_name_for_profile`.

**Resolver**: `feeds/resolver.try_resolve_feed_with_website_fallback` calls `detect_platform_from_careers_page` when slug-only resolution fails (seed, hn_hiring, github). **Discovery settings helpers**: `discovery/settings.py` (`discovery_enabled`, `max_companies_per_source`, `enabled_discovery_sources`).

## Env
- `JOB_SEARCH_PROFILE`: `effective_profile_id` after CLI `--profile` (`pipeline/config_paths.py`).
- `JOB_SEARCH_PROFILE_DASHBOARD`: dashboard lifespan only (`dashboard/api.py` → `effective_profile_id`).

## Shared state & side effects
- **SQLite** `db_path`: `listings`, `companies`, `discovery_runs`; `connect()` runs `ensure_schema` (db/schema.sql + db/migrations/*.sql) each open.
- **Logs**: `~/Library/Logs/job-search-agent/pipeline.log`, `discovery.log`, `ollama_metrics.log`.
- **Secrets**: `settings.yaml` profiles.* (webhooks, SMTP, ntfy topic).

## Failure modes
- Ollama down/timeout → scorer returns None (listing unscored); HN comment skipped; tailor HTTP 502 with detail dict; relevance LLM failure → score 50 (may still pass threshold).
- Per-feed errors isolated in monitor; broken feed stops pipeline ingestion for that company.
- Tailor: missing `experience-dossier.md` or resume docx → error string; one-page trim skipped if LibreOffice missing (`find_soffice` None).
- JSON/schema validation failures after retries → skip or API error.
