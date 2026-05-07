# Experience Dossier

**Usage:** Source for resume tailoring: each project is a `##` heading with `### Subtitles` (tailor picks one for `Name — Subtitle`). **`### Outcomes`** and **`### What I built / did`** hold quotable metrics; **`Personal skills`** is an inventory—tailor subsets per job, do not paste wholesale.

**Roles:** Software intern / new grad / entry-level — full-stack, backend, automation, mobile, DevOps-adjacent (Toronto / Canada).

**Do not invent:** team size (solo unless noted), uptime/SLA/latency numbers, employer names for these projects.

## Personal skills

**Languages:** Python, TypeScript, JavaScript, SQL, Java, C++, C, Swift  
**Frameworks:** React, FastAPI, Next.js, Node.js, SwiftUI, Tailwind, Vite, CustomTkinter, Pandas, NumPy, OpenCV, Radix UI, Zod  
**Infra & tools:** PostgreSQL, SQLite, Supabase, Docker, Git, REST, pytest, GitHub Actions, systemd, launchd, Caddy, Ollama, Gemini API, Cloudinary, Shopify Admin API, Win32 API, PyInstaller  
**AI workflow:** Cursor, Claude Code, Antigravity; agentic IDE patterns  

**Courses:** DSA, OOP, systems, linear algebra, discrete math, probability/stats, calculus *(for the education line on the Word template—do not paste this heading into project bullets)*

---

## JobRadar

**Date:** Apr 2026–present

### Subtitles
- ATS Job Feed Monitor with LLM Scoring
- Async ETL Pipeline for Job Listing Feeds
- React and FastAPI Job Search Dashboard
- Local Ollama Fit Ranking and Resume Tailor Agent
- Scheduled Job Feed Discovery Automation System

### Type
Personal project (public repo).

### One-line summary
Local job-search stack: ingest ATS RSS/JSON feeds, discover employers, score listings with Ollama, SQLite storage, React dashboard for triage and Word/PDF resume tailoring from this dossier.

### Problem / goal
Avoid manual feed checks and paid cloud LLMs; one-machine automation with optional ntfy/Slack/email alerts.

### What I built / did
- Async feed monitor (httpx, feedparser) with per-feed isolation.
- Parsers/normalizers for Greenhouse, Lever, Ashby, Workable-style feeds; title, location, salary, date fields.
- Discovery: seeded companies, YC directory, HN “Who’s Hiring” + structured LLM assist; verified feed URLs in SQLite.
- Scoring: dedup by hash, profile-driven Ollama prompts with JSON validation/retries; fit, preference, competitiveness → weighted overall.
- FastAPI + React/TS/Vite UI: listings, company feed health, re-score, resume tailor → Word template from markdown dossier.
- macOS launchd for pipeline + discovery; setup scripts, venv, DB init, optional model pull.
- 90+ pytest tests (HTTP/LLM mocked): feeds, dedup, scoring, discovery, config, docx tailor; `pyproject.toml` package layout.

### Stack & tools
Python 3.12, FastAPI, Uvicorn, React, TypeScript, Vite, SQLite, httpx, feedparser, ollama client, PyYAML, pytest, WordprocessingML (docx), LibreOffice headless (PDF path), launchd

### Scope & constraints
Solo; single-user Mac + SQLite; no multi-tenant hosting; no cloud LLM fallback in-repo; LLM quality depends on local hardware.

### Outcomes
- Scheduled pipeline + daily discovery without manual feed polling.
- $0 recurring LLM API cost for scoring/tailoring (local Ollama).
- Single codebase for discovery → ingest → score → review → tailored export.

### JD keywords
Python, FastAPI, React, TypeScript, SQLite, RSS, ETL, Ollama, LLM, pytest, async, full-stack, automation, macOS, ATS, docx, REST

---

## ClashTracker

**Date:** Jun 2025–present

### Subtitles
- FastAPI and React Clan Analytics Dashboard
- Scheduled ETL with PostgreSQL Dashboard Backend
- Multi-Router REST API for the Analytics Dashboard
- React Dashboard SPA with CI/CD Pipeline
- Systemd-Scheduled Dashboard Data Ingestion

### Type
Personal project (private repo).

### One-line summary
Clash of Clans analytics: scheduled httpx ingestion from Supercell API → Supabase/PostgreSQL, FastAPI REST, React/TS SPA for clan leadership.

### Problem / goal
Replace manual war, Legends, and Capital Raid checks across many clans with one searchable, historical dashboard.

### What I built / did
- FastAPI: CORS, Pydantic error handling, lifecycle logging; nine routers (dashboard, wars, raids, legends, players, tracked clans/players, admin, health).
- Ingestion: httpx + Supabase client, systemd timer (~144 runs/day), tag encoding, timeouts, namespaced logs.
- Schema: 13 incremental SQL migrations (Supabase).
- React 19 SPA: TS, Vite, Tailwind v4, Radix UI, react-router-dom — 10 pages, shared components.
- CI: GitHub Actions → build/deploy SPA to GitHub Pages; API via DuckDNS host.
- Oracle Cloud VM: systemd units, Caddy reverse proxy + TLS, setup scripts.

### Stack & tools
FastAPI, React 19, TypeScript, Vite, Tailwind v4, Radix UI, PostgreSQL, Supabase, httpx, GitHub Actions, systemd, Caddy, pytest

### Scope & constraints
Solo; single VM; no Docker in-repo.

### Outcomes
- ~200 users (clan alliance); ~250 API calls per ingestion cycle; 20k+ rows.
- ~30 clans, ~500 players tracked; ~144 ingest runs/day.
- ~5–8 hrs/week saved vs manual checks for a co-lead.

### JD keywords
FastAPI, React, TypeScript, PostgreSQL, Supabase, REST, CI/CD, systemd, migrations, scheduled ingestion, Oracle Cloud, full-stack

---

## VisionLoop

**Date:** Sept 2025–present

### Subtitles
- OpenCV Template-Matching Automation Bot
- Threaded Win32 Desktop Controller
- Computer-Vision Input Simulation Engine
- Python GUI with Local LLM
- Event-Driven Window Automation System

### Type
Personal project (public repo).

### One-line summary
Windows desktop automation: OpenCV template matching, Win32 `SendMessage`/`PrintWindow` capture, threaded control loop, CustomTkinter UI, optional local LLaMA for ambiguous vision states.

### Problem / goal
Automate repetitive UI cycles in a fixed game client—timed, resumable runs without global cursor dependency.

### What I built / did
- Timed runs (presets 5–20 min), 900s session cap, home-screen recovery, cooperative stop via threading events.
- Vision: OpenCV template match, bottom-half ROI, confidence thresholds for state detection.
- Win32: target child HWND, DPI-aware APIs, `PrintWindow` frames (no screen scraping).
- Input: `SendMessage` clicks/drags, Bezier mouse paths, stop polling between steps.
- CustomTkinter GUI: daemon worker thread, after-idle status updates, optional DWM taskbar thumbnail.
- JSON config singleton + pyautogui-based screen adaptation.
- Local LLaMA hook for ambiguous pipeline states.
- PyInstaller packaging.

### Stack & tools
Python 3.8+, OpenCV, NumPy, Pillow, CustomTkinter, PyInstaller, pyautogui, Win32 API, JSON, threading, LLaMA (local)

### Scope & constraints
Solo; Windows-only fixed client; no automated test suite (manual/ad-hoc).

### Outcomes
- ~20 min session: ~6–10 full cycles, ~150–500 automated UI actions (vs ~25–50 manual interactions per cycle).
- Typical use ~3–7 hrs/week attention reclaimed (1–2 sessions/day at 15–20 min).

### JD keywords
Python, OpenCV, Windows API, desktop automation, threading, computer vision, PyInstaller, local LLM

---

## ReturnClip

**Date:** Mar 2026

### Subtitles
- SwiftUI and Next.js Returns Prototype
- Multi-Surface Hackathon Full-Stack App
- iOS Return Flow with Gemini API
- Shopify Refund Integration Backend
- Collaborative Three-Layer E-Commerce System

### Type
Hackathon — Hack Canada 2026 (Reactiv ClipKit Lab); team; under 24h.

### One-line summary
Returns flow: SwiftUI iOS (deep link by order ID), Next.js 15 API (Zod, Gemini condition summary, Shopify refund when configured), React merchant dashboard, Cloudinary uploads.

### Problem / goal
Shorten returns from long form/email to: scan → reason → photo → AI summary → decision on mobile.

### What I built / did
- SwiftUI app: URL deep links, multi-step return flow.
- iOS services: Cloudinary upload + Gemini REST (documented mock path); smoke-test notes.
- Next.js: evidence upload, AI assessment, decision + execution handlers; shared TS types with clients.
- Shopify Admin API: order lookup + refund when credentials present.
- Merchant UI: React + Vite, Cloudinary React, case list/detail/media viewer.
- Supabase SQL migration: merchants, cases, evidence, decisions, executions (idempotency keys), audit. **Demo runtime:** in-memory store; schema = target model.
- Team: agreed REST contracts + shared types before integration; shared GitHub repo.

### Stack & tools
Swift, SwiftUI, Next.js 15, React, TypeScript, Zod, Vite, Cloudinary, Gemini REST, Supabase/Postgres (schema), Shopify Admin API, URLSession

### Scope & constraints
Hackathon timeline; demo backend in-memory; no Docker/CI in-repo; Gemini 429 under load in recorded tests; Cloudinary upload passed in smoke tests.

### Outcomes
- Target UX: ~30s mobile path vs ~15–30 min legacy flow (design intent).
- Dashboard triage ~15–25 cases/hr (UX target).
- Idempotent execution collapses duplicate refund retries from double-tap/retry storms.

### JD keywords
Swift, SwiftUI, iOS, Next.js, React, TypeScript, REST, Zod, Shopify, Gemini, Cloudinary, Supabase, idempotency, hackathon, full-stack
