# Experience Dossier

**How to use:** This file is the single source of truth for all projects and experiences. A separate resume-tailoring step will read this file plus a target job description, then select which projects to include and what bullets to write into a fixed Word template with several project/bullet slots.

**Target roles:** Software engineering intern / new-grad / entry-level positions (Toronto / Canada focus). Likely fits: full-stack web, backend, desktop/automation, mobile, DevOps-adjacent roles.

**Boundaries — do not invent:**
- Team sizes — all projects below are solo unless noted otherwise.
- Uptime, SLA, or latency numbers — none are instrumented.
- Employer names — none of the projects below are employer-affiliated.

---

## Clash AutoLoot

**Aliases:** Vision-Driven Desktop Automation Bot · OpenCV Game-Client Automation Tool · Win32 UI Automation Engine · Automated Farming Bot with Local LLM Integration

### Type
Personal project.

### One-line summary
Windows desktop bot that automates repetitive Clash of Clans farming loops using computer-vision template matching and Win32 message-based input.

### Problem / goal
Eliminate repetitive manual clicking through identical attack–end–home cycles in the PC version of Clash of Clans, letting the user step away while the bot farms resources on a timed or star-bonus-capped schedule.

### What I built / did
- Designed and implemented the core farming loop: timed runs with configurable presets (5/10/15/20 min), a 900-second star-bonus hard cap, automatic home-screen recovery, and a `threading.Event`-based cooperative stop mechanism.
- Built a vision pipeline using `cv2.matchTemplate` with bottom-half ROI cropping and confidence thresholds to detect in-game buttons and the star-bonus icon, driving all bot decisions.
- Wrote a Win32 window-management layer that finds the game's `CROSVM_1` child HWND, calls DPI-aware APIs, and captures frames via `PrintWindow` — no global cursor dependency.
- Implemented input simulation through `SendMessageW` for clicks and drags, with Bezier-curve mouse movement and stop-event polling between steps for responsive cancellation.
- Created a CustomTkinter GUI that launches the bot on a daemon thread and uses `tk.after` polling for live status updates, with an optional DWM taskbar-thumbnail overlay.
- Centralized coordinate resolution through a singleton config that reads `templates/data.json` and adapts to screen size via `pyautogui.size()`.
- Integrated a locally hosted LLaMA model to improve in-game decision stability during the automation loop.

### Stack & tools
Python 3.8+, OpenCV (`cv2.matchTemplate`), NumPy, Pillow, CustomTkinter, PyInstaller, pyautogui, Win32 API (`SendMessageW`, `PrintWindow`, HWND management), JSON configuration, LLaMA (local inference), `threading`, `logging` (rotating file handler)

### Scope & constraints
- Solo developer; single-repo Python application.
- Targets a fixed game-client window on Windows; no cross-platform support.
- No formal test suite observed (`testing123.py` is an ad-hoc script).
- `_handle_walls` is a stub (`pass`) — wall-upgrade automation is unimplemented.
- README states MIT license; no `LICENSE` file in-repo.
- No CI/CD, Dockerfile, or cloud deployment.

### Outcomes
- Reduced manual workflows by ~60% through structured automation and event-driven control logic.
- Improved decision stability by ~75% after integrating a locally hosted LLaMA model.
- A 20-minute session completes roughly 6–10 full attack cycles, each replacing ~25–50 manual interactions, yielding ~150–500 automated UI actions per session.
- For a solo user running 1–2 sessions/day at 15–20 minutes each, reclaims about 3–7 hours/week of continuous attention.

### JD keywords
Python, OpenCV, template matching, NumPy, Windows API, SendMessage, HWND, PrintWindow, desktop automation, CustomTkinter, threading, daemon thread, ROI, JSON configuration, PyInstaller, PIL/Pillow, pyautogui, logging, computer vision, Win32, LLaMA, local LLM inference

---

## Clash of Clans Tracker (Analytics Dashboard)

**Aliases:** Real-Time Game Analytics Dashboard · Full-Stack Data Ingestion Platform · Automated Monitoring & Reporting Pipeline · Community Analytics SPA · Scheduled ETL & REST API Service

### Type
Personal project (README: "Private project").

### One-line summary
Full-stack analytics platform that ingests Clash of Clans game data on a schedule, stores it in PostgreSQL via Supabase, exposes a FastAPI REST API, and renders a React + TypeScript SPA for clan leadership.

### Problem / goal
Clan co-leads were spending hours each week manually checking war results, Legends League standings, and Capital Raid performance across dozens of clans. This project consolidates that data into a single searchable dashboard with historical tracking.

### What I built / did
- Architected and built the FastAPI backend with CORS, Pydantic validation-error handlers, and structured request-lifecycle logging.
- Implemented nine domain routers (`apps/api/routers/`): dashboard, wars, raids, legends, players, tracked clans, tracked players, admin, and health.
- Wrote a Python ingestion service using `httpx` and `supabase-py` that pulls data from the Supercell CoC API on a systemd timer (~144 runs/day), with tag encoding, timeouts, and structured `coc.*` log namespaces.
- Designed and evolved the PostgreSQL schema across 13 migration files in `supabase/migrations/`.
- Built a shared config module and per-request Supabase client factory (`apps/shared/config.py`, `apps/api/database.py`).
- Developed the React 19 SPA with TypeScript, Vite, Tailwind v4, Radix UI, and react-router-dom — 10 pages and 7 reusable components.
- Set up CI via GitHub Actions to build and deploy the frontend to GitHub Pages on push to `main`, with `VITE_API_URL` pointing to a DuckDNS hostname.
- Created VM deployment assets: systemd service/timer units, a Caddyfile for reverse proxy + TLS, and setup scripts, deployed on an Oracle Cloud VM.

### Stack & tools
FastAPI, Uvicorn, React 19, TypeScript, Vite, Tailwind CSS v4, Radix UI, react-router-dom, PostgreSQL, Supabase, httpx, Python, GitHub Actions, GitHub Pages, systemd, Caddy, Oracle Cloud VM, pytest, structured logging

### Scope & constraints
- Solo developer.
- Deployed on a single Oracle Cloud VM; no containerization or horizontal scaling.
- No Dockerfile or docker-compose in-repo.

### Outcomes
- 200+ users across a mid-size clan alliance using the dashboard/API for clan operations.
- ~250 API requests per ingestion cycle; 20k+ database records.
- ~30 tracked clans, ~500 tracked players, ~144 automated ingestion runs/day.
- Saved ~5–8 hours/week versus manual war/Legends/Capital checks for a co-lead.

### JD keywords
FastAPI, Uvicorn, React, TypeScript, Vite, Tailwind CSS, Radix UI, PostgreSQL, Supabase, REST API, httpx, Python, GitHub Actions, GitHub Pages, systemd, Caddy, structured logging, pytest, CI/CD, Oracle Cloud, scheduled ingestion, database migrations, full-stack

---

## ReturnClip

**Aliases:** AI-Powered Returns Platform · E-Commerce Return Processing System · Cross-Platform Return Management App · Shopify Returns & Refund Integration · Mobile-First AI Condition Assessment Tool

### Type
Hackathon — built at Hack Canada 2026 (Reactiv ClipKit Lab track); cited in README and SUBMISSION.md.

### One-line summary
Multi-surface return-processing prototype spanning a SwiftUI iOS app, a Next.js API with AI condition assessment, and a React merchant dashboard, with optional Shopify order/refund integration.

### Problem / goal
Post-purchase returns typically involve slow form-and-email workflows that frustrate shoppers and consume merchant support time. ReturnClip shortens the path to: scan order → select reason → snap photo → get AI condition summary → receive refund/exchange decision — all within a short mobile interaction.

### What I built / did
- Built the SwiftUI iOS application entry point with URL-based order-ID deep linking and a multi-step return experience flow (`ReturnClipKit/ReturnClipKit/Experience/`, `Screens/`).
- Implemented client-side service layer calling Cloudinary (image upload) and Gemini (condition assessment) REST APIs, with a mock-fallback path documented and tested in `tests/API_TEST_RESULTS.md`.
- Designed and built the Next.js 15 return-processing pipeline: evidence upload, AI assessment, decision engine, and execution endpoints (`backend/src/app/api/returns/`), with Zod request validation and shared TypeScript types.
- Integrated Shopify Admin API for order lookup and refund execution when merchant credentials are configured.
- Built a React + Vite merchant dashboard with Cloudinary React for media viewing, case list, case detail, and return-media viewer components.
- Authored a Postgres schema (Supabase migration) covering merchants, cases, evidence, decisions, executions (with idempotency keys), and audit tables. The live backend uses an in-memory Map store annotated as a Phase-D placeholder, so the SQL schema represents the target data model, not the runtime store during the hackathon demo.

### Stack & tools
Swift 5.0, SwiftUI, iOS (Xcode / `project.yml`), Next.js 15, React 19, TypeScript, Zod, Vite 6, Cloudinary (upload + React SDK), Gemini REST API (`gemini-2.0-flash`), Supabase, PostgreSQL, JSONB, Shopify Admin API, URLSession, REST

### Scope & constraints
- Hackathon timeline (Hack Canada 2026); ownership unclear beyond personal claim — team composition not stated in-repo.
- No Dockerfile, CI/CD, or cloud deployment config in-repo; hosting is unknown.
- Backend runtime is in-memory (`db.ts`), not the Postgres schema, at demo time.
- Gemini API hit a 429 rate limit during recorded smoke tests; Cloudinary upload passed.

### Outcomes
- Reduced return processing time from ~15–30 minutes (legacy form-and-email) to ~30 seconds via the clip-style mobile flow.
- Merchant case-triage throughput of ~15–25 cases/hour through the dashboard UX.
- Idempotency-key design collapses 3–5 duplicate execute requests (mobile double-tap / flaky retry) to a single logical refund.
- API smoke tests recorded (March 7, 2026): Cloudinary upload pass, Gemini key valid (rate-limited under load).

### JD keywords
Swift, SwiftUI, iOS, Next.js, React, TypeScript, REST API, Zod, Supabase, PostgreSQL, JSONB, Shopify Admin API, Gemini, Cloudinary, URLSession, idempotency, merchant dashboard, hackathon, mobile development, full-stack, AI/LLM integration, deep linking, image upload, case lifecycle
