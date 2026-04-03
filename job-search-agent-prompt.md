# Automated job search AI system — Claude Code build prompt

## What you're building

A fully automated, 24/7 job search pipeline that runs on a dedicated Mac Studio (M4 Max, 32GB unified memory). The system scrapes job listings on a schedule, scores each one using a local LLM, stores ranked results in a database, serves a dashboard for review, and sends push alerts for high-scoring matches. Everything runs locally with zero API costs.

## Hardware context

- **Machine**: Mac Studio, Apple M4 Max, 32GB unified memory, always-on, macOS
- **Inference capability**: Can run quantized models up to ~14B Q4 comfortably via `ollama` with Metal GPU acceleration. Expect 2–5 seconds per job listing at this size. 8B models will be faster (~1–2s) if throughput matters more than quality.
- **Network**: Standard residential connection. Scrapers need rate limiting and polite delays to avoid IP bans. No proxy infrastructure assumed — add guidance for optional proxy rotation later.
- **Storage**: Local SSD, plenty of space. SQLite is fine — no need for a database server.

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Mac Studio (always-on)                                         │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐   ┌─────────┐ │
│  │ Scrapers │──▶│ Dedup +  │──▶│ LLM scorer   │──▶│ SQLite  │ │
│  │ (cron)   │   │ normalize│   │ (ollama)     │   │         │ │
│  └──────────┘   └──────────┘   └──────────────┘   └────┬────┘ │
│                                       ▲                 │      │
│                                       │                 ▼      │
│                                 profile.yaml     ┌──────────┐  │
│                                                  │Dashboard │  │
│                                                  │Streamlit │  │
│                                                  └──────────┘  │
│                                                       │        │
│                                                  ┌──────────┐  │
│                                                  │ Alerts   │  │
│                                                  │ntfy/Slack│  │
│                                                  └──────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Project structure

```
job-search-agent/
├── config/
│   ├── profile.yaml          # User profile, skills, preferences, weights
│   ├── sources.yaml          # Scraper targets, URLs, selectors, schedules
│   └── settings.yaml         # Thresholds, alert config, model config
├── scrapers/
│   ├── base.py               # Abstract scraper with rate limiting, retry, UA rotation
│   ├── linkedin.py           # LinkedIn-specific scraper
│   ├── indeed.py             # Indeed-specific scraper
│   ├── glassdoor.py          # Glassdoor-specific scraper
│   └── career_pages.py       # Generic career page scraper (configurable selectors)
├── pipeline/
│   ├── dedup.py              # Deduplication by hashing title+company+location
│   ├── normalizer.py         # Normalize fields (salary ranges, locations, remote status)
│   ├── scorer.py             # LLM scoring orchestrator (calls ollama, parses JSON)
│   └── alerter.py            # Sends notifications via ntfy.sh, Slack, email
├── prompts/
│   ├── scoring_system.txt    # System prompt for the scoring LLM
│   └── scoring_user.txt      # User prompt template with {{profile}} and {{listing}} slots
├── dashboard/
│   └── app.py                # Streamlit dashboard
├── db/
│   ├── schema.sql            # SQLite schema
│   └── migrations/           # Schema migrations if needed
├── scripts/
│   ├── setup.sh              # One-shot install script (brew, ollama, python deps)
│   ├── run_pipeline.py       # Main entry point — scrape, dedup, score, alert
│   └── install_launchd.sh    # Installs macOS launchd plist for scheduling
├── tests/
│   ├── test_scorer.py        # Test scoring with sample listings
│   ├── test_dedup.py         # Test deduplication logic
│   └── fixtures/             # Sample job listings for testing
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Component specifications

### 1. Scrapers (`scrapers/`)

**Base scraper class** must provide:
- Configurable rate limiting (default: 2–5 second random delay between requests)
- User-agent rotation from a realistic browser UA list
- Retry with exponential backoff (3 retries, 5s/15s/45s)
- Request logging (URL, status code, timestamp) for debugging
- Return a list of `RawListing` dataclass objects

**RawListing dataclass**:
```python
@dataclass
class RawListing:
    source: str              # "linkedin", "indeed", "glassdoor", "career_page"
    source_url: str          # Original listing URL
    title: str
    company: str
    location: str            # Raw location string
    description: str         # Full job description text
    salary_raw: str | None   # Raw salary string if present
    posted_date: str | None  # Raw date string if present
    scraped_at: datetime
    raw_html: str            # Full HTML for re-parsing later
```

**Scraper-specific notes**:
- **LinkedIn**: Use `playwright` (async) for JavaScript rendering. Target the job search results page and individual listing pages. Respect LinkedIn's robots.txt and rate limit aggressively (5–10s delays). Consider using LinkedIn's RSS feeds as a less aggressive alternative.
- **Indeed**: `httpx` + `selectolax` may work for many listings since Indeed server-renders. Fall back to `playwright` if needed.
- **Glassdoor**: Requires `playwright` — heavy JavaScript. May need cookie/session handling.
- **Career pages**: Configurable via `sources.yaml` — user provides base URL, CSS selectors for listing links, title, description, etc. Use `httpx` + `selectolax`.

**sources.yaml example**:
```yaml
linkedin:
  enabled: true
  search_queries:
    - "backend engineer remote"
    - "staff software engineer Toronto"
  filters:
    date_posted: "past_week"
    remote: true

indeed:
  enabled: true
  search_queries:
    - "senior software engineer"
  location: "Toronto, ON"

career_pages:
  - name: "Stripe"
    url: "https://stripe.com/jobs/search"
    selectors:
      listing_link: "a.JobsListings__listingLink"
      title: "h1.JobsDescription__title"
      description: "div.JobsDescription__description"
```

### 2. Deduplication and normalization (`pipeline/`)

**Dedup strategy**:
- Generate a hash from `normalize(title) + normalize(company) + normalize(city)` where `normalize()` lowercases, strips whitespace, removes punctuation
- Before scoring any listing, check if this hash exists in the database
- If it exists and was scored within the last 7 days, skip entirely
- If it exists but is older than 7 days, re-score (the listing may have been reposted, or your profile may have changed)

**Normalization**:
- **Salary**: Parse strings like "$150k-$180k", "$150,000 - $180,000/yr", "150-180K CAD" into a structured `SalaryRange(min=150000, max=180000, currency="CAD", period="annual")`. If no salary is listed, set to `None` — the LLM will factor this into the preference score.
- **Location**: Extract city, state/province, country. Detect remote indicators ("Remote", "Anywhere", "Distributed").
- **Posted date**: Parse relative dates ("2 days ago", "posted today") into absolute datetimes.

### 3. LLM scorer (`pipeline/scorer.py` + `prompts/`)

This is the most important component. The LLM replaces hundreds of lines of brittle rule-based code.

**Model**: `qwen3:14b` via `ollama`. Pull it during setup. If scoring speed is a concern, `llama3.1:8b-instruct-q4_K_M` is faster but slightly less nuanced.

**Scoring approach**: Send the LLM a structured prompt containing:
1. The full user profile (from `profile.yaml`)
2. The full job listing (title, company, description, salary, location)
3. Explicit instructions to return JSON with three scores and reasoning

**System prompt** (`prompts/scoring_system.txt`):
```
You are a job matching analyst. You will receive a candidate profile and a job listing. Your task is to evaluate the match across three dimensions and return a structured JSON response.

Scoring dimensions (each 0–100):

1. FIT SCORE — How well does the candidate's skills and experience match what this role requires?
   - 90–100: Candidate exceeds all requirements
   - 70–89: Strong match, meets most requirements
   - 50–69: Partial match, meets some requirements
   - 30–49: Weak match, significant gaps
   - 0–29: Poor match, lacks key requirements

2. PREFERENCE SCORE — How well does this role align with the candidate's stated preferences?
   - Consider: salary range, location/remote policy, company size, industry, role type, seniority level
   - Deal-breakers (marked in profile) should result in a score of 0 regardless of other factors
   - Missing information (e.g., no salary listed) should not be penalized heavily — score based on what IS available

3. COMPETITIVENESS SCORE — How likely is the candidate to stand out among other applicants?
   - Consider: Does the candidate meet ALL required qualifications? How many nice-to-have skills do they have? Is their seniority level an exact match, overqualified, or underqualified? How niche are their matching skills?
   - A perfect match on all requirements + rare skills = high score
   - Meeting only the minimum with common skills = low score

For each score, provide a 1–2 sentence justification explaining the key factors.

IMPORTANT:
- Be calibrated. A score of 80+ should mean genuine strong match, not just "the listing mentions some of the same technologies."
- Factor in context. "3+ years of Go" matches "5 years building microservices in Go" even though the exact phrasing differs.
- Be honest about gaps. If the candidate lacks a key requirement, reflect that in the fit score even if other factors are strong.

Respond with ONLY valid JSON, no markdown fences, no preamble:
{
  "fit_score": <int 0-100>,
  "fit_reason": "<string>",
  "pref_score": <int 0-100>,
  "pref_reason": "<string>",
  "comp_score": <int 0-100>,
  "comp_reason": "<string>"
}
```

**User prompt template** (`prompts/scoring_user.txt`):
```
## CANDIDATE PROFILE
{{profile}}

## JOB LISTING
Title: {{title}}
Company: {{company}}
Location: {{location}}
Salary: {{salary or "Not specified"}}
Remote: {{remote_status or "Not specified"}}

### Full Description
{{description}}
```

**Scorer implementation notes**:
- Use `ollama`'s Python client library (`ollama` pip package) with `format="json"` to enforce JSON output
- Set `temperature=0.1` for consistent scoring (low creativity, high precision)
- Implement a timeout of 30 seconds per listing — if the model hangs, log it and skip
- Parse the JSON response, validate that all three scores are integers 0–100
- If parsing fails, retry once with the same input. If it fails again, log the raw response and skip the listing.
- Calculate the overall weighted score in Python: `overall = w1 * fit + w2 * pref + w3 * comp` (defaults: 0.4 / 0.35 / 0.25)

### 4. Profile configuration (`config/profile.yaml`)

```yaml
# Candidate profile — this gets injected into every scoring prompt
name: "Your Name"

summary: |
  Senior backend engineer with 5 years of experience building distributed systems.
  Strong in Go, Python, and PostgreSQL. Experience with Kubernetes, gRPC, and event-driven architectures.
  Looking for a senior or staff-level IC role at a product-focused company.

skills:
  expert:
    - Go
    - Python
    - PostgreSQL
    - REST API design
  proficient:
    - Kubernetes
    - Docker
    - gRPC
    - Redis
    - Kafka
  familiar:
    - Rust
    - TypeScript
    - Terraform
    - AWS (EC2, S3, Lambda, RDS)

experience_years: 5

education:
  - degree: "B.Sc. Computer Science"
    school: "University of Toronto"

preferences:
  target_titles:
    - "Senior Software Engineer"
    - "Senior Backend Engineer"
    - "Staff Software Engineer"
  salary_floor: 150000        # CAD, annual. Listings below this get pref_score penalty.
  salary_currency: "CAD"
  locations:
    - "Toronto"
    - "Remote"
    - "Remote (Canada)"
  remote_preference: "remote_preferred"  # "remote_only", "remote_preferred", "hybrid_ok", "onsite_ok"
  company_size_preference: "mid_to_large"  # "startup", "mid_to_large", "enterprise", "any"
  industries_preferred:
    - "fintech"
    - "developer tools"
    - "cloud infrastructure"

  deal_breakers:                # Any of these = pref_score of 0
    - "defense contractor"
    - "requires US security clearance"
    - "on-site only"
    - "unpaid"
    - "internship"

scoring_weights:
  fit: 0.40
  preference: 0.35
  competitiveness: 0.25

alert_threshold: 78            # Send a push notification if overall score >= this
```

### 5. Database schema (`db/schema.sql`)

```sql
CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT UNIQUE NOT NULL,           -- dedup hash (title+company+location)
    source TEXT NOT NULL,                -- "linkedin", "indeed", etc.
    source_url TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location_raw TEXT,
    location_city TEXT,
    location_country TEXT,
    remote_status TEXT,                  -- "remote", "hybrid", "onsite", "unknown"
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT,
    description TEXT,
    raw_html TEXT,
    posted_date TEXT,

    -- LLM scores
    fit_score INTEGER,
    fit_reason TEXT,
    pref_score INTEGER,
    pref_reason TEXT,
    comp_score INTEGER,
    comp_reason TEXT,
    overall_score REAL,

    -- Metadata
    status TEXT DEFAULT 'new',           -- "new", "reviewing", "applied", "rejected", "expired"
    notes TEXT,                          -- User's personal notes
    scored_at TEXT,
    scraped_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_overall_score ON listings(overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_source ON listings(source);
CREATE INDEX IF NOT EXISTS idx_created_at ON listings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_company ON listings(company);
```

### 6. Alerting (`pipeline/alerter.py`)

**Primary: ntfy.sh** (zero setup, free, push to phone):
```python
import httpx

def send_ntfy(title: str, company: str, score: float, url: str):
    httpx.post(
        "https://ntfy.sh/YOUR_TOPIC_NAME_HERE",
        headers={
            "Title": f"Job match: {score:.0f}% — {title}",
            "Click": url,
            "Tags": "briefcase",
            "Priority": "high" if score >= 90 else "default",
        },
        content=f"{company}\nFit: {fit} | Pref: {pref} | Comp: {comp}"
    )
```

**Optional: Slack incoming webhook** — just a `POST` to a webhook URL with a JSON body. Configure the webhook URL in `settings.yaml`.

**Optional: Email via SMTP** — use `smtplib` with a Gmail app password or any SMTP server. Send a daily digest of all listings scored above threshold, rather than one email per listing.

### 7. Dashboard (`dashboard/app.py`)

Build with **Streamlit**. It runs on `localhost:8501` and is accessible from any device on the local network.

**Features**:
- Sortable, filterable table of all scored listings
- Filter sliders for each sub-score (fit, pref, comp, overall)
- Filter dropdowns for status, source, remote status
- Click a row to expand: shows full description, all three score reasons, source URL link
- Inline status update buttons: New → Reviewing → Applied / Rejected
- A notes text field per listing
- Summary stats at the top: total listings today, average score, count by source
- Chart: score distribution histogram (how many listings at each score bracket)
- Chart: listings over time (by day, colored by source)
- A "re-score" button that re-runs a single listing through the LLM with current profile

### 8. Scheduling (`scripts/install_launchd.sh`)

Use macOS `launchd` (not cron) for reliability. The plist should:
- Run `run_pipeline.py` every 3 hours
- Log stdout/stderr to `~/Library/Logs/job-search-agent/`
- Set `KeepAlive` to false (run on schedule, not continuously)
- Set working directory to the project root

**Plist location**: `~/Library/LaunchAgents/com.jobsearch.agent.plist`

The install script should:
1. Generate the plist with correct paths
2. Copy it to `~/Library/LaunchAgents/`
3. Run `launchctl load` to activate it
4. Verify it's scheduled with `launchctl list`

### 9. Setup script (`scripts/setup.sh`)

One-shot install that handles everything:
```bash
# 1. Install Homebrew dependencies
brew install python@3.12 ollama

# 2. Start ollama and pull model
ollama serve &    # or check if already running
ollama pull qwen3:14b

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Playwright browsers (for LinkedIn/Glassdoor)
playwright install chromium

# 5. Initialize database
sqlite3 db/jobs.db < db/schema.sql

# 6. Prompt user to edit config/profile.yaml
echo "Edit config/profile.yaml with your skills, preferences, and deal-breakers."

# 7. Install launchd schedule
bash scripts/install_launchd.sh
```

## Implementation priorities

Build in this order so each component is testable independently:

1. **Database schema + profile.yaml** — foundation everything else depends on
2. **Scorer** — the core differentiator. Test it with hardcoded sample listings before connecting scrapers. Get the prompt right first.
3. **One scraper** (Indeed is easiest) — prove the full pipeline end-to-end
4. **Alerting** (ntfy.sh) — immediate gratification, takes 10 minutes
5. **Dashboard** — makes everything visible and usable
6. **Remaining scrapers** — LinkedIn, Glassdoor, career pages
7. **Scheduling** — launchd plist for hands-off operation
8. **Setup script** — polish for repeatability

## Error handling requirements

- **Scraper failures**: Log the error, skip the source, continue with other sources. Never let one broken scraper kill the entire pipeline run.
- **LLM failures**: If ollama is not running, attempt to start it. If the model isn't pulled, pull it. If scoring a specific listing fails twice, log it and move on.
- **Database errors**: Use transactions. If a batch of inserts fails, roll back and log.
- **Network errors**: All HTTP requests should have timeouts (30s for scraping, 60s for ollama). Retry with backoff.
- **Pipeline logging**: Use Python's `logging` module with both console output and a rotating file handler (`~/Library/Logs/job-search-agent/pipeline.log`). Log level INFO by default, DEBUG when a `--verbose` flag is passed.

## Testing strategy

- **Scorer tests**: Include 5–10 sample job listings in `tests/fixtures/` as JSON files. Test that the scorer returns valid JSON, that scores are integers 0–100, and that the overall score calculation is correct. Optionally, assert that a clearly-good-match listing scores above 70 and a clearly-bad-match listing scores below 40.
- **Dedup tests**: Test that identical listings produce the same hash, and that minor variations (extra whitespace, different casing) also produce the same hash.
- **Normalizer tests**: Test salary parsing with various formats. Test location parsing. Test date parsing.
- **Integration test**: Run the full pipeline against a mocked scraper that returns fixture data, and verify that results end up in the database with valid scores.

## Dependencies (`requirements.txt`)

```
httpx>=0.27
selectolax>=0.3
playwright>=1.40
ollama>=0.4
streamlit>=1.30
pyyaml>=6.0
```

## Things to watch out for

- **LinkedIn anti-scraping**: LinkedIn is aggressive about blocking scrapers. Start with their RSS feeds or public job search pages. Don't log in or use authenticated endpoints. If you get 429s, back off significantly.
- **Ollama memory**: The 14B Q4 model uses ~10GB of unified memory. Leave headroom for the OS and other processes. If memory pressure is an issue, drop to the 8B model.
- **Score calibration**: The LLM may score too generously at first. Include calibration guidance in the system prompt (the scoring rubric above). You may need to iterate on the prompt 3–5 times with real listings to get well-calibrated scores.
- **Salary data**: Most listings don't include salary. The scorer should handle "Not specified" gracefully — slight penalty in preference score, not a zero.
- **Listing expiry**: Listings get taken down. Consider a periodic "freshness check" that marks old listings as expired if their source URL returns a 404.
