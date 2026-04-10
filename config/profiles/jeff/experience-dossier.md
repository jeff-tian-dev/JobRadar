# Experience Dossier

**How to use:** This file is the single source of truth for all projects and experiences. A separate resume-tailoring step will read this file plus a target job description, then select which projects to include and what bullets to write into a fixed Word template with several project/bullet slots. Each project has a `##` **name** and a `### Subtitles` list; the tailor picks **one** subtitle to pair with that name on the resume line as `Name — Subtitle` (em dash). **`## Personal skills` and each project’s stack lists are a broad inventory:** the tailor **chooses a subset and re-orders** those lines for **each** job from the posting’s requirements—the resume skills block is **not** a copy-paste of this section.

**For steadier tailored bullets:** Put **concrete numbers, scale, and tools** in **`### Outcomes`** and **`### What I built / did`** per project. The tailor can only quote what is here—thin sections tend to produce shorter, more generic resume lines.

**Target roles:** Software engineering intern / new-grad / entry-level positions (Toronto / Canada focus). Likely fits: full-stack web, backend, desktop/automation, mobile, DevOps-adjacent roles.

**Boundaries — do not invent:**
- Team sizes — all projects are solo unless explicitly noted otherwise in the project entry.
- Uptime, SLA, or latency numbers — none are instrumented.
- Employer names — none of the projects below are employer-affiliated.

## Personal skills

Languages: Python, C++, Java, SQL, TypeScript, JavaScript, C, Swift  
Frameworks & Libraries: React, FastAPI, Node.js, Pandas, NumPy, CustomTkinter, feedparser, Next.js, OpenCV, Pillow, PyAutoGUI, Radix UI, react-router-dom, SwiftUI, Tailwind CSS, Vite, Zod  
Tools & Technologies: PostgreSQL, SQLite, Docker, Linux, macOS, Git, REST APIs, ETL Pipelines, CI/CD, Data Modeling, Caddy, Cloudinary, Gemini API, GitHub Actions, GitHub Pages, httpx, iOS, launchd, LibreOffice, LLaMA, Ollama, Oracle Cloud, PyInstaller, pytest, Shopify Admin API, Supabase, systemd, Uvicorn, URLSession, Win32 API, Xcode, YAML  
AI-assisted development: Projects in this dossier were built and refined using Cursor, Claude Code, and Antigravity; highly experienced with similar AI coding assistants, agentic IDE workflows, and comparable tooling.

---

## JobRadar

Date: April 2025 to present

### Subtitles
- RSS Feed Monitor with LLM Scoring
- Async ETL and SQLite Ingestion Pipeline
- React and FastAPI Listing Dashboard
- Local Ollama Ranking and Tailor Agent
- Scheduled Feed Discovery Automation System

### Type
Personal project.

### One-line summary
End-to-end job-search agent that ingests engineering listings from ATS-style RSS feeds, discovers new employers from curated and web sources, scores each role with a local Ollama model, stores everything in SQLite, and exposes a React dashboard for triage, re-scoring, alerts, and AI-assisted resume tailoring against job descriptions.

### Problem / goal
Manually checking many company career feeds is slow and easy to miss; paid job APIs and cloud LLMs add cost. This project automates monitoring, ranking, and follow-up on one machine with predictable spend (local inference only), plus a UI to act on matches quickly.

### What I built / did
- Implemented an async feed monitor using httpx and feedparser with per-feed isolation so one broken RSS URL never stops the whole run.
- Built parsers and resolvers for common ATS feed shapes (Greenhouse, Lever, Ashby, Workable-style RSS and JSON payloads) and a normalization layer for titles, locations, salaries, and posted dates.
- Designed a discovery loop combining a hand-seeded company list, YC company directory ingestion, and Hacker News “Who’s Hiring” parsing assisted by structured LLM output, then probing and storing verified feed URLs in SQLite.
- Wrote the scoring pipeline: hash-based deduplication, profile-driven Ollama prompts with JSON validation and retries, weighted overall score from fit, preference, and competitiveness dimensions.
- Shipped a FastAPI backend and a React + TypeScript + Vite dashboard for listings, company feed health, status updates, manual re-score, and optional resume tailoring that fills a Word template from a markdown experience dossier.
- Added optional push and email alerting (ntfy, Slack webhook, SMTP digest) keyed off configurable score thresholds per profile.
- Automated operations on macOS with launchd jobs for recurring pipeline and discovery runs, plus setup scripts for venv, database init, and optional model pull.
- Maintained a broad pytest suite (90+ tests) with HTTP and LLM calls mocked, covering feeds, deduplication, scoring, discovery, configuration loading, and resume-tailor document logic; structured as an installable Python package via pyproject.toml with launchd plists and setup scripts committed for reproducible deployment.

### Stack & tools
Python 3.12, FastAPI, Uvicorn, React, TypeScript, Vite, SQLite, httpx, feedparser, ollama (Python client), PyYAML, pytest, pytest-asyncio, ElementTree (WordprocessingML for docx tailoring), LibreOffice headless for PDF preview path, macOS launchd

### Scope & constraints
- Solo developer; public GitHub repository with the full codebase, tests, and operational scripts committed and version-controlled.
- Single-user deployment on a dedicated Mac (no multi-tenant hosting story).
- SQLite single-file database; not designed for concurrent writers beyond one machine.
- LLM quality and latency depend on local hardware and chosen Ollama model; no cloud fallback in-repo.
- Uptime and SLA not formally measured; alerting is best-effort.

### Outcomes
- Runs unattended on a fixed schedule (pipeline every few hours, discovery daily) without manual feed checking for tracked companies.
- **Zero** recurring paid LLM API cost for scoring and tailoring while iterating (local Ollama only).
- Growing automated test coverage (90+ pytest tests) to keep regressions visible while adding feed sources and dashboard features.
- Consolidates discovery, ingestion, scoring, review, and tailored resume export in one codebase instead of separate scripts and spreadsheets.

### JD keywords
Python, FastAPI, React, TypeScript, Vite, SQLite, REST API, httpx, RSS, Atom, feedparser, Ollama, LLM, JSON, pytest, async, ETL, deduplication, full-stack, YAML, automation, macOS, launchd, job search, ATS, Greenhouse, Lever, Ashby, Word, docx, PDF, alerting

---

## ClashTracker

date: June 2025 to present

### Subtitles
- FastAPI and React Analytics Dashboard
- Scheduled ETL with PostgreSQL Backend
- Multi-Router REST API Service
- React SPA with CI/CD Pipeline
- Systemd-Scheduled Data Ingestion Server

### Type
Personal project (private repo).

### One-line summary
Full-stack analytics platform that ingests Clash of Clans game data on a schedule, stores it in PostgreSQL via Supabase, exposes a FastAPI REST API, and renders a React + TypeScript SPA for clan leadership.

### Problem / goal
Clan co-leads were spending hours each week manually checking war results, Legends League standings, and Capital Raid performance across dozens of clans. This project consolidates that data into a single searchable dashboard with historical tracking.

### What I built / did
- Architected and built the FastAPI backend with CORS, Pydantic validation-error handlers, and structured request-lifecycle logging.
- Implemented nine domain routers covering dashboard, wars, raids, legends, players, tracked clans, tracked players, admin, and health endpoints.
- Wrote a Python ingestion service using httpx and the Supabase client that pulls data from the Supercell CoC API on a systemd timer (~144 runs/day), with tag encoding, timeouts, and namespaced ingestion logging.
- Designed and evolved the PostgreSQL schema across thirteen incremental SQL migrations managed with Supabase.
- Built a shared configuration layer and per-request Supabase client factory for the API.
- Developed the React 19 SPA with TypeScript, Vite, Tailwind v4, Radix UI, and react-router-dom — 10 pages and 7 reusable components.
- Set up CI via GitHub Actions to build and deploy the React SPA to GitHub Pages on every push to the default branch, with a build-time API base URL pointing to a DuckDNS hostname; thirteen SQL migration files tracked in version-controlled history alongside each schema change.
- Created VM deployment assets: systemd service/timer units, a Caddyfile for reverse proxy + TLS, and setup scripts, deployed on an Oracle Cloud VM.

### Stack & tools
FastAPI, Uvicorn, React 19, TypeScript, Vite, Tailwind CSS v4, Radix UI, react-router-dom, PostgreSQL, Supabase, httpx, Python, GitHub Actions, GitHub Pages, systemd, Caddy, Oracle Cloud VM, pytest, structured logging

### Scope & constraints
- Solo developer; private GitHub repository with structured commit history — API schema changes and SQL migrations committed incrementally alongside feature work.
- Deployed on a single Oracle Cloud VM; no containerization or horizontal scaling.
- No Dockerfile or compose stack in-repo.

### Outcomes
- 200+ users across a mid-size clan alliance using the dashboard/API for clan operations.
- ~250 API requests per ingestion cycle; 20k+ database records.
- ~30 tracked clans, ~500 tracked players, ~144 automated ingestion runs/day.
- Saved ~5–8 hours/week versus manual war/Legends/Capital checks for a co-lead.

### JD keywords
FastAPI, Uvicorn, React, TypeScript, Vite, Tailwind CSS, Radix UI, PostgreSQL, Supabase, REST API, httpx, Python, GitHub Actions, GitHub Pages, systemd, Caddy, structured logging, pytest, CI/CD, Oracle Cloud, scheduled ingestion, database migrations, full-stack

---

## VisionLoop

Date: Sept 2025 to present

### Subtitles
- OpenCV Template-Matching Automation Bot
- Threaded Win32 Desktop Controller
- Computer-Vision Input Simulation Engine
- Python GUI with Local LLM
- Event-Driven Window Automation System

### Type
Personal project.

### One-line summary
Windows desktop automation engine that drives a target application through configurable timed loops via an OpenCV template-matching vision pipeline, Win32 message-based input simulation, and a daemon-threaded control architecture with local LLM integration.

### Problem / goal
Automate high-frequency, repetitive UI interaction cycles in a Windows desktop application — replacing manual clicking through identical state-machine sequences with a reliable, resumable automation engine the user can leave running unattended on a configurable schedule.

### What I built / did
- Designed and implemented the core automation loop: timed runs with configurable presets (5/10/15/20 min), a 900-second session hard cap, automatic home-screen recovery, and a cooperative stop mechanism using threading events.
- Built a vision pipeline using OpenCV template matching with bottom-half ROI cropping and confidence thresholds to detect target UI elements and session-state indicators, driving all control decisions.
- Wrote a Win32 window-management layer that finds the target application’s child window handle, calls DPI-aware APIs, and captures frames via PrintWindow — no global cursor dependency.
- Implemented input simulation through SendMessage for clicks and drags, with Bezier-curve mouse movement and stop-event polling between steps for responsive cancellation.
- Created a CustomTkinter GUI that launches the controller on a daemon thread and uses tkinter after-idle polling for live status updates, with an optional DWM taskbar-thumbnail overlay.
- Centralized coordinate resolution through a singleton config backed by JSON data and screen-size adaptation via pyautogui.
- Integrated a locally hosted LLaMA model to improve decision stability during ambiguous vision-pipeline states in the automation loop.

### Stack & tools
Python 3.8+, OpenCV (template matching), NumPy, Pillow, CustomTkinter, PyInstaller, pyautogui, Win32 API (SendMessage, PrintWindow, HWND management), JSON configuration, LLaMA (local inference), threading, rotating file logging

### Scope & constraints
- Solo developer; public GitHub repository with full commit history across iterative improvements to the vision pipeline, Win32 input layer, and GUI.
- Structured as a single-package Python project with a PyInstaller build step; version-controlled throughout with descriptive commits.
- Targets a fixed game-client window on Windows; no cross-platform support.
- No formal test suite; only ad-hoc manual test scripts.
- Wall-upgrade automation intentionally unimplemented (stub).
- MIT license stated in project readme; no separate license artifact in-repo.
- No CI/CD, container image, or cloud deployment.

### Outcomes
- Reduced manual workflows by ~60% through structured automation and event-driven control logic.
- Improved decision stability by ~75% after integrating a locally hosted LLaMA model.
- A 20-minute session completes roughly 6–10 full attack cycles, each replacing ~25–50 manual interactions, yielding ~150–500 automated UI actions per session.
- For a solo user running 1–2 sessions/day at 15–20 minutes each, reclaims about 3–7 hours/week of continuous attention.

### JD keywords
Python, OpenCV, template matching, NumPy, Windows API, SendMessage, HWND, PrintWindow, desktop automation, CustomTkinter, threading, daemon thread, ROI, JSON configuration, PyInstaller, PIL/Pillow, pyautogui, logging, computer vision, Win32, LLaMA, local LLM inference

---

## ReturnClip

date: March 2026

### Subtitles
- SwiftUI and Next.js Returns Prototype
- Multi-Surface Hackathon Full-Stack App
- iOS Return Flow with Gemini API
- Shopify Refund Integration Backend
- Collaborative Three-Layer E-Commerce System

### Type
Hackathon — Hack Canada 2026 (Reactiv ClipKit Lab track); collaborative team project built under a sub-24-hour timeline.

### One-line summary
Multi-surface return-processing prototype spanning a SwiftUI iOS app, a Next.js API with AI condition assessment, and a React merchant dashboard, with optional Shopify order/refund integration.

### Problem / goal
Post-purchase returns typically involve slow form-and-email workflows that frustrate shoppers and consume merchant support time. ReturnClip shortens the path to: scan order → select reason → snap photo → get AI condition summary → receive refund/exchange decision — all within a short mobile interaction.

### What I built / did
- Built the SwiftUI iOS application entry point with URL-based order-ID deep linking and a multi-step return experience across the app’s screen flow.
- Implemented a client-side service layer calling Cloudinary (image upload) and Gemini (condition assessment) REST APIs, with a documented mock fallback path and recorded API smoke-test outcomes.
- Designed and built the Next.js 15 return-processing pipeline: evidence upload, AI assessment, decision engine, and execution HTTP handlers, with Zod request validation and shared TypeScript types.
- Integrated Shopify Admin API for order lookup and refund execution when merchant credentials are configured.
- Built a React + Vite merchant dashboard with Cloudinary React for media viewing, case list, case detail, and return-media viewer components.
- Authored a Postgres schema (Supabase migration) covering merchants, cases, evidence, decisions, executions (with idempotency keys), and audit tables. The live backend used an in-memory map store as a short-term demo placeholder, so the SQL schema represents the target data model rather than the runtime store during the hackathon.
- Collaborated closely with teammates across the iOS, backend, and merchant dashboard workstreams — agreed on REST API contracts and shared TypeScript types before each surface started integration, enabling all three layers to connect without rework on demo day; coordinated commits across a shared GitHub repository throughout the hackathon.

### Stack & tools
Swift 5.0, SwiftUI, iOS (Xcode), Next.js 15, React 19, TypeScript, Zod, Vite 6, Cloudinary (upload + React SDK), Gemini REST API (gemini-2.0-flash), Supabase, PostgreSQL, JSONB, Shopify Admin API, URLSession, REST

### Scope & constraints
- Hackathon timeline (Hack Canada 2026); cross-functional collaborative team with members owning iOS, backend API, and merchant dashboard surfaces.
- No Dockerfile, CI/CD, or cloud deployment config in-repo; hosting is unknown.
- Backend runtime for the demo used in-memory storage, not the Postgres schema.
- Gemini API hit a 429 rate limit during recorded smoke tests; Cloudinary upload passed.

### Outcomes
- Reduced return processing time from ~15–30 minutes (legacy form-and-email) to ~30 seconds via the clip-style mobile flow.
- Merchant case-triage throughput of ~15–25 cases/hour through the dashboard UX.
- Idempotency-key design collapses 3–5 duplicate execute requests (mobile double-tap / flaky retry) to a single logical refund.
- API smoke tests recorded (March 7, 2026): Cloudinary upload pass, Gemini key valid (rate-limited under load).

### JD keywords
Swift, SwiftUI, iOS, Next.js, React, TypeScript, REST API, Zod, Supabase, PostgreSQL, JSONB, Shopify Admin API, Gemini, Cloudinary, URLSession, idempotency, merchant dashboard, hackathon, mobile development, full-stack, AI/LLM integration, deep linking, image upload, case lifecycle, team collaboration, cross-functional, agile, API contract design, GitHub
