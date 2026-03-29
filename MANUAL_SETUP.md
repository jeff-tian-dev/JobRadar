# Manual setup checklist (JobRadar / job search agent)

Do these steps on your **Mac Studio** (production). On Windows you can still edit configs and run tests; scheduling and default log paths assume macOS.

## One-time machine setup

1. **Install Ollama**  
   - Install from [ollama.com](https://ollama.com) or via Homebrew (`brew install ollama` if your `setup.sh` uses that).  
   - Ensure the Ollama app/service is running (menu bar on Mac, or `ollama serve` if you run it manually).

2. **Pull the scoring model**  
   ```bash
   ollama pull qwen2.5:14b-instruct-q4_K_M
   ```  
   Optional faster model (if you change config later): `llama3.1:8b-instruct-q4_K_M`.

3. **Install Python 3.12**  
   Per project: Homebrew `python@3.12` or another 3.12 install you prefer.

4. **Install Playwright Chromium** (needed for JS-heavy scrapers)  
   After Python deps:  
   ```bash
   playwright install chromium
   ```

5. **Initialize the database** (if you do not rely solely on `setup.sh`)  
   ```bash
   sqlite3 db/jobs.db < db/schema.sql
   ```

## Project configuration (you edit these)

6. **`config/profile.yaml`**  
   Replace the example with your real summary, skills, preferences, deal-breakers, and `scoring_weights` / `alert_threshold`. Do not commit secrets here; it’s your resume-like profile.

7. **`config/settings.yaml`** (create from example if provided)  
   - Model name (must match what you pulled in Ollama).  
   - ntfy topic URL or topic name, Slack webhook, SMTP settings — **keep this file out of git** if it holds secrets.

8. **`config/sources.yaml`**  
   Enable/disable sources, search queries, locations, and career-page URLs/selectors.

## Scheduling and logs (Mac)

9. **Log directory** (if the app expects it and it does not exist yet)  
   ```bash
   mkdir -p ~/Library/Logs/job-search-agent
   ```

10. **Install the launchd job** (after paths in the script match your clone location)  
    ```bash
    bash scripts/install_launchd.sh
    ```  
    Confirm with `launchctl list | grep jobsearch` (or whatever label the plist uses).

## Ongoing checks before a pipeline run

11. **Ollama is running** and the configured model is available (`ollama list`).

12. **Network** — residential IP; if a site rate-limits you, increase delays in scraper config rather than bypassing ToS.

## Dashboard (when implemented)

13. Start locally:  
    ```bash
    streamlit run dashboard/app.py
    ```  
    Open the URL Streamlit prints (e.g. `http://localhost:8501`).

## Optional / later

14. **Listing freshness** — Periodically review or automate marking stale listings `expired` if URLs 404 (may be a follow-up feature).

15. **Prompt tuning** — If scores feel too high/low, adjust `prompts/scoring_system.txt` after testing with real listings (coordinate with whoever maintains the repo; treat prompt changes like code changes).

---

**Summary:** You manually install Ollama + pull the model, install Python/Playwright, create/edit YAML configs (especially profile + secrets), ensure log dir exists, load launchd, and keep Ollama running before scheduled or manual pipeline runs.
