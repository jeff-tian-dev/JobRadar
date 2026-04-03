#!/usr/bin/env python3
"""Fetch RSS feeds → dedup/normalize → score → SQLite → alerts."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Repo root on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from feeds.monitor import fetch_all_active_feeds
from pipeline.alerter import maybe_alert_listing, send_daily_email_digest_if_enabled
from pipeline.config_paths import (
    db_path,
    effective_profile_id,
    load_profile_for_scoring,
    load_settings,
)
from pipeline.db import connect, get_by_hash, scored_within_days, update_scores, upsert_listing_after_scrape
from pipeline.dedup import listing_dedup_hash
from pipeline.normalizer import (
    detect_remote_status,
    extract_city_country,
    is_posted_older_than_days,
    parse_posted_date,
    parse_salary,
)
from pipeline.scorer import score_listing, scores_to_db_dict


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    log_dir = Path.home() / "Library/Logs/job-search-agent"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pipeline.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    fh = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)


def _max_listing_age_days(settings: dict) -> int | None:
    """Default 7; None in YAML disables age filtering."""
    raw = settings.get("max_listing_age_days", 7)
    if raw is None:
        return None
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return 7
    return n if n >= 0 else None


_DEFAULT_TITLE_KEYWORDS: list[str] = [
    "engineer", "developer", "data scientist", "data analyst", "data engineer",
    " ml ", "machine learning", "infrastructure", "platform engineer",
    "architect", "backend", "frontend", "fullstack", "full-stack", "full stack",
    "software", "sre", "devops", "site reliability",
    "security engineer", "security researcher", "appsec", "product manager",
    "technical program", "scientist", "analytics engineer",
    "research engineer", "research scientist", "ai engineer", " llm",
    "cloud engineer", "cloud architect", "reliability engineer",
    "intern", "internship", "co-op", "coop", "new grad", "new graduate",
    "junior", "entry level", "entry-level",
]


_SENIORITY_EXCLUDE: list[str] = [
    "senior", " sr ", "sr.", "staff ", "principal", " lead ",
    "manager", "director", " vp ", "vice president", "head of",
    "distinguished", "fellow", "architect",  # architect roles typically need years of exp
]

_ENTRY_LEVEL_TERMS: list[str] = [
    "intern", "internship", "co-op", "coop", "co op",
    "new grad", "new graduate", "junior", "entry level", "entry-level",
]

_TORONTO_TERMS: list[str] = ["toronto", "ontario", " on,", "on, ca", "canada"]


def _title_matches_keywords(title: str, keywords: list[str]) -> bool:
    t = " " + title.lower() + " "   # pad so whole-word checks work for short tokens
    return any(kw in t for kw in keywords)


def _is_senior_title(title: str, exclude: list[str]) -> bool:
    t = " " + title.lower() + " "
    return any(kw in t for kw in exclude)


def _location_ok(location: str | None, toronto_terms: list[str]) -> bool:
    """Keep listings in Toronto/Ontario/Canada area, or with no location (often remote)."""
    if not location:
        return True  # unspecified — keep (may be remote or globally open)
    loc = location.lower()
    return any(term in loc for term in toronto_terms)


def _title_keywords(settings: dict) -> list[str]:
    return settings.get("title_keywords", _DEFAULT_TITLE_KEYWORDS)


def _seniority_exclude(settings: dict) -> list[str]:
    return settings.get("seniority_exclude", _SENIORITY_EXCLUDE)


def _toronto_terms(settings: dict) -> list[str]:
    return settings.get("toronto_terms", _TORONTO_TERMS)


def _entry_level_terms(settings: dict) -> list[str]:
    return settings.get("entry_level_terms", _ENTRY_LEVEL_TERMS)


def raw_to_db_payload(raw, h: str, company_id: int | None = None) -> dict:
    sal = parse_salary(raw.salary_raw)
    city, country = extract_city_country(raw.location)
    remote = detect_remote_status(raw.title, raw.location, raw.description)
    posted = parse_posted_date(raw.posted_date)
    scraped_at = raw.scraped_at.isoformat()
    return {
        "hash": h,
        "source": raw.source,
        "source_url": raw.source_url,
        "title": raw.title,
        "company": raw.company,
        "location_raw": raw.location,
        "location_city": city,
        "location_country": country,
        "remote_status": remote,
        "salary_min": sal.min if sal else None,
        "salary_max": sal.max if sal else None,
        "salary_currency": sal.currency if sal else None,
        "description": raw.description,
        "raw_html": raw.raw_html[:500_000],
        "posted_date": posted,
        "scraped_at": scraped_at,
        "fit_score": None,
        "fit_reason": None,
        "pref_score": None,
        "pref_reason": None,
        "comp_score": None,
        "comp_reason": None,
        "overall_score": None,
        "status": "new",
        "notes": None,
        "scored_at": None,
        "company_id": company_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="JobRadar pipeline")
    parser.add_argument("--profile", type=str, default=None, help="Profile id (overrides env/settings)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    setup_logging(args.verbose)
    log = logging.getLogger("run_pipeline")

    profile_id = effective_profile_id(args.profile)
    settings = load_settings()
    try:
        profile = load_profile_for_scoring(profile_id, settings)
    except FileNotFoundError as e:
        log.error("%s", e)
        return 1

    dpath = db_path(settings)
    digest_lines: list[str] = []
    max_age = _max_listing_age_days(settings)
    title_kws = _title_keywords(settings)
    senior_excl = _seniority_exclude(settings)
    toronto_kws = _toronto_terms(settings)
    entry_kws = _entry_level_terms(settings)

    with connect(dpath) as conn:
        raw_listings = asyncio.run(fetch_all_active_feeds(conn, settings))
        log.info("Collected %s raw listings from RSS feeds", len(raw_listings))

        for i, raw in enumerate(raw_listings):
            if i > 0 and i % 50 == 0:
                conn.commit()
                log.info("Progress: %d/%d listings processed", i, len(raw_listings))

            if not _title_matches_keywords(raw.title, title_kws):
                log.debug("Skip (title filter): %s | %s", raw.title, raw.company)
                continue

            if not _title_matches_keywords(raw.title, entry_kws):
                log.debug("Skip (not entry-level): %s | %s", raw.title, raw.company)
                continue

            if not _location_ok(raw.location, toronto_kws):
                log.debug("Skip (location filter): %s | %s | loc=%r", raw.title, raw.company, raw.location)
                continue

            if max_age is not None and is_posted_older_than_days(raw.posted_date, max_age):
                log.info(
                    "Skip (posted older than %sd): %s | %s | posted=%r",
                    max_age,
                    raw.title,
                    raw.company,
                    raw.posted_date,
                )
                continue
            h = listing_dedup_hash(raw.title, raw.company, raw.location)
            row = get_by_hash(conn, h)
            payload = raw_to_db_payload(raw, h)
            try:
                upsert_listing_after_scrape(conn, payload)
            except Exception:
                log.exception("DB upsert failed for %s", h)
                continue

            # Always refresh description/raw_html from the feed even when we skip rescoring.
            if row is not None and scored_within_days(row, days=7):
                log.info("Skip (scored within 7d): %s | %s", raw.title, raw.company)
                continue

            sal = parse_salary(raw.salary_raw)
            salary_display = raw.salary_raw or "Not specified"
            if sal and sal.min is not None:
                salary_display = f"{sal.min}-{sal.max} {sal.currency or ''} ({sal.period})".strip()

            remote_display = payload["remote_status"] or "Not specified"

            sr = score_listing(
                profile,
                raw.title,
                raw.company,
                raw.location or "Not specified",
                salary_display,
                remote_display,
                raw.description,
                settings=settings,
            )
            if sr is None:
                log.warning("Scoring skipped/failed: %s", raw.title)
                continue
            try:
                update_scores(conn, h, scores_to_db_dict(sr))
            except Exception:
                log.exception("DB score update failed for %s", h)
                continue

            maybe_alert_listing(
                settings,
                profile_id,
                profile,
                raw.title,
                raw.company,
                sr.overall_score,
                sr.fit_score,
                sr.pref_score,
                sr.comp_score,
                raw.source_url,
            )
            if sr.overall_score >= float(profile.get("alert_threshold", 78)):
                digest_lines.append(
                    f"- {sr.overall_score:.0f}% {raw.title} @ {raw.company} — {raw.source_url or ''}"
                )

    try:
        send_daily_email_digest_if_enabled(settings, profile_id, digest_lines)
    except Exception:
        log.exception("Email digest failed")

    log.info("Pipeline finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
