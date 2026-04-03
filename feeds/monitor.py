"""Fetch active RSS feeds from the companies table and produce RawListing objects."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any

import httpx

from feeds.parser import (
    FeedEntry,
    greenhouse_job_detail_api_url,
    parse_ashby_json,
    parse_feed_xml,
    parse_greenhouse_json,
    parse_greenhouse_listing_url,
    parse_lever_json,
    strip_html_to_plain,
)
from pipeline.company_db import (
    get_active_feed_companies,
    increment_feed_failures,
    update_feed_status,
    update_feed_success,
)
from pipeline.models import RawListing

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_DEFAULT_MAX_FAILURES = 5
_DEFAULT_CONCURRENCY = 20  # simultaneous feed fetches
_GREENHOUSE_DETAIL_CONCURRENCY = 10  # per-company parallel job-detail fetches


async def _enrich_greenhouse_descriptions(
    client: httpx.AsyncClient,
    entries: list[FeedEntry],
    timeout: float,
) -> list[FeedEntry]:
    """Fill empty descriptions from Greenhouse per-job API (board list omits content)."""

    async def _one(entry: FeedEntry) -> FeedEntry:
        if entry.description.strip():
            return entry
        parsed = parse_greenhouse_listing_url(entry.url)
        if not parsed:
            return entry
        board_slug, job_id = parsed
        detail_url = greenhouse_job_detail_api_url(board_slug, job_id)
        try:
            dr = await client.get(detail_url, timeout=timeout, follow_redirects=True)
            dr.raise_for_status()
            payload = dr.json()
            if not isinstance(payload, dict):
                return entry
            content = payload.get("content") or ""
            if not content:
                return entry
            plain = strip_html_to_plain(content)[:5000]
            if not plain:
                return entry
            return FeedEntry(
                title=entry.title,
                url=entry.url,
                company=entry.company,
                location=entry.location,
                description=plain,
                published=entry.published,
            )
        except Exception:
            logger.exception(
                "Greenhouse job detail fetch failed: %s (%s)",
                entry.title,
                detail_url,
            )
            return entry

    sem = asyncio.Semaphore(_GREENHOUSE_DETAIL_CONCURRENCY)

    async def _guarded(e: FeedEntry) -> FeedEntry:
        async with sem:
            return await _one(e)

    return list(await asyncio.gather(*[_guarded(e) for e in entries]))


def _entry_to_raw_listing(entry: FeedEntry, platform: str) -> RawListing:
    """Convert a FeedEntry to a RawListing."""
    return RawListing(
        source=platform,
        source_url=entry.url,
        title=entry.title,
        company=entry.company,
        location=entry.location,
        description=entry.description,
        salary_raw=None,
        posted_date=entry.published,
        scraped_at=datetime.now(timezone.utc),
        raw_html="",  # RSS feeds don't have separate raw_html; description is already plain text
    )


async def fetch_feed(
    client: httpx.AsyncClient,
    company_row: sqlite3.Row,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list[RawListing]:
    """Fetch and parse one company's feed into RawListing objects.

    Handles RSS/Atom (Ashby, Workable) and JSON APIs (Greenhouse, Lever).
    """
    feed_url: str = company_row["feed_url"]
    company_name: str = company_row["name"]
    platform: str = company_row["feed_platform"] or "unknown"

    logger.info("Fetching feed for %s (%s)", company_name, feed_url)
    r = await client.get(feed_url, timeout=timeout, follow_redirects=True)
    r.raise_for_status()

    # Route to the right parser based on platform and content-type
    content_type = r.headers.get("content-type", "")
    entries: list[FeedEntry] = []

    if platform == "ashby":
        try:
            data = r.json()
            if isinstance(data, dict) and "jobPostings" in data:
                entries = parse_ashby_json(data, company_name)
            else:
                entries = parse_feed_xml(r.text, company_name, platform)
        except Exception:
            logger.warning("Ashby JSON parse failed for %s, falling back to RSS", company_name)
            entries = parse_feed_xml(r.text, company_name, platform)
    elif platform == "greenhouse" or ("json" in content_type and platform not in ("workable",)):
        try:
            data = r.json()
            if isinstance(data, dict) and "jobs" in data:
                entries = parse_greenhouse_json(data, company_name)
                entries = await _enrich_greenhouse_descriptions(client, entries, timeout)
            elif isinstance(data, list):
                entries = parse_lever_json(data, company_name)
        except Exception:
            logger.warning("JSON parse failed for %s, falling back to RSS", company_name)
            entries = parse_feed_xml(r.text, company_name, platform)
    else:
        # RSS/Atom: Workable or unknown
        entries = parse_feed_xml(r.text, company_name, platform)

    logger.info("Parsed %d entries from %s feed", len(entries), company_name)
    return [_entry_to_raw_listing(entry, platform) for entry in entries]


async def fetch_all_active_feeds(
    conn: sqlite3.Connection,
    settings: dict[str, Any] | None = None,
) -> list[RawListing]:
    """Fetch all active company feeds and return a combined list of RawListing objects.

    Failures on individual feeds are logged and skipped; the feed failure counter
    is incremented. After max_consecutive_failures, the feed is marked 'broken'.
    """
    settings = settings or {}
    feed_cfg = settings.get("feeds", {})
    timeout = float(feed_cfg.get("fetch_timeout_seconds", _DEFAULT_TIMEOUT))
    max_failures = int(feed_cfg.get("max_consecutive_failures", _DEFAULT_MAX_FAILURES))
    concurrency = int(feed_cfg.get("fetch_concurrency", _DEFAULT_CONCURRENCY))

    companies = get_active_feed_companies(conn)
    if not companies:
        logger.info("No active feeds to fetch")
        return []

    logger.info("Fetching %d active feeds (concurrency=%d)", len(companies), concurrency)

    results: list[tuple[int, str, list[RawListing] | Exception]] = []
    sem = asyncio.Semaphore(concurrency)

    async def _fetch_one(company: sqlite3.Row) -> tuple[int, str, list[RawListing] | Exception]:
        company_id = int(company["id"])
        company_name = company["name"]
        async with sem:
            try:
                listings = await fetch_feed(client, company, timeout=timeout)
                return company_id, company_name, listings
            except Exception as e:
                return company_id, company_name, e

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "JobRadar/1.0 RSS monitor (https://github.com/jobradar)",
            "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
        }
    ) as client:
        results = await asyncio.gather(*[_fetch_one(c) for c in companies])

    all_listings: list[RawListing] = []
    for company_id, company_name, outcome in results:
        if isinstance(outcome, Exception):
            logger.warning("Feed fetch failed for %s: %s", company_name, outcome)
            failures = increment_feed_failures(conn, company_id)
            if failures >= max_failures:
                logger.warning(
                    "Marking %s feed as broken after %d consecutive failures",
                    company_name,
                    failures,
                )
                update_feed_status(conn, company_id, "broken")
        else:
            update_feed_success(conn, company_id)
            all_listings.extend(outcome)

    conn.commit()
    logger.info("Collected %d listings from %d feeds", len(all_listings), len(companies))
    return all_listings
