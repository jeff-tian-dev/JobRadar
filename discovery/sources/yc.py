"""Discover companies from Y Combinator's public company directory."""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from typing import Any

import httpx

from feeds.resolver import FEED_URL_PATTERNS, verify_feed_url

_PROBE_PLATFORMS = ["greenhouse", "lever", "ashby"]
from pipeline.company_db import finish_discovery_run, insert_discovery_run, upsert_company

logger = logging.getLogger(__name__)

_YC_API_URL = "https://yc-oss.github.io/api/companies/all.json"
_CONCURRENCY = 20  # simultaneous Greenhouse checks


def _slug_from_url(url: str) -> str | None:
    m = re.search(r"https?://(?:www\.)?([^/]+)", url)
    if m:
        return m.group(1).split(".")[0]
    return None


async def _check_any_platform(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    company: dict[str, Any],
    timeout: float,
) -> tuple[dict[str, Any], str | None, str | None, int]:
    """Try Greenhouse → Lever → Ashby and return the first working feed.

    Returns (company_data, feed_url_or_None, platform_or_None, entry_count).
    """
    name = company.get("name", "").strip()
    website = company.get("url") or company.get("website") or ""
    slug = company.get("slug") or _slug_from_url(website)
    if not slug:
        return company, None, None, 0

    async with sem:
        for platform in _PROBE_PLATFORMS:
            url = FEED_URL_PATTERNS[platform].format(slug=slug)
            ok, count = await verify_feed_url(client, url, timeout=timeout)
            if ok:
                return company, url, platform, count

    return company, None, None, 0


async def discover_from_yc(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    max_companies: int | None = None,  # None = all ~5,600
) -> int:
    """Fetch all YC companies and concurrently probe their Greenhouse feeds.

    Returns the number of companies added with active feeds.
    """
    run_id = insert_discovery_run(conn, "yc")
    conn.commit()

    feed_cfg = settings.get("feeds", {})
    feed_timeout = float(feed_cfg.get("fetch_timeout_seconds", 10.0))
    disc_cfg = settings.get("discovery", {})
    concurrency = int(disc_cfg.get("yc_concurrency", _CONCURRENCY))

    async with httpx.AsyncClient(
        headers={"User-Agent": "JobRadar/1.0 (https://github.com/jobradar)"}
    ) as client:
        try:
            r = await client.get(_YC_API_URL, timeout=20.0)
            r.raise_for_status()
            companies = r.json()
        except Exception as e:
            logger.warning("Failed to fetch YC company list: %s", e)
            finish_discovery_run(conn, run_id, 0, 0, status="failed", error=str(e))
            conn.commit()
            return 0

        if max_companies is not None:
            companies = companies[:max_companies]

        logger.info("Checking Greenhouse feeds for %d YC companies (concurrency=%d)", len(companies), concurrency)

        sem = asyncio.Semaphore(concurrency)
        tasks = [_check_any_platform(client, sem, c, feed_timeout) for c in companies]
        results = await asyncio.gather(*tasks)

    with_feeds = 0
    for company, feed_url, feed_platform, entry_count in results:
        name = company.get("name", "").strip()
        if not name:
            continue
        website = company.get("url") or company.get("website") or None
        slug = company.get("slug") or _slug_from_url(website or "")
        description = company.get("one_liner") or company.get("long_description") or None
        batch = company.get("batch") or None

        record: dict[str, Any] = {
            "name": name,
            "slug": slug,
            "website": website,
            "description": f"[{batch}] {description or ''}" if batch else description,
            "industry": company.get("industry") or None,
            "discovery_source": "yc",
        }

        if feed_url and feed_platform:
            record["feed_url"] = feed_url
            record["feed_platform"] = feed_platform
            record["feed_status"] = "active"
            with_feeds += 1
            logger.debug("YC %s → %d jobs", name, entry_count)
        else:
            record["feed_status"] = "no_feed"

        upsert_company(conn, record)

    conn.commit()
    finish_discovery_run(conn, run_id, companies_found=len(results), companies_with_feeds=with_feeds)
    conn.commit()
    logger.info("YC discovery complete: %d companies checked, %d with Greenhouse feeds", len(results), with_feeds)
    return with_feeds
