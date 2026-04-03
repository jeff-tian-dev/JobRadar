"""Import seed companies from config/seed_companies.yaml and resolve their feeds."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

import httpx

from feeds.resolver import try_resolve_feed
from pipeline.company_db import (
    finish_discovery_run,
    get_company_by_name,
    insert_discovery_run,
    upsert_company,
)
from pipeline.config_paths import load_seed_companies

logger = logging.getLogger(__name__)


async def discover_from_seed(
    conn: sqlite3.Connection,
    settings: dict[str, Any] | None = None,
) -> int:
    """Import companies from seed_companies.yaml; resolve and verify their feeds.

    Returns the number of companies successfully added or updated with active feeds.
    """
    settings = settings or {}
    seed_companies = load_seed_companies()
    if not seed_companies:
        logger.info("No seed companies found in config/seed_companies.yaml")
        return 0

    logger.info("Processing %d seed companies", len(seed_companies))
    run_id = insert_discovery_run(conn, "seed")
    conn.commit()

    found = 0
    with_feeds = 0
    feed_cfg = settings.get("feeds", {})
    timeout = float(feed_cfg.get("fetch_timeout_seconds", 15.0))

    async with httpx.AsyncClient() as client:
        for company_data in seed_companies:
            name = company_data.get("name", "")
            slug = company_data.get("slug", "")
            platform = company_data.get("platform")

            if not name or not slug:
                logger.warning("Seed company missing name or slug: %r", company_data)
                continue

            found += 1

            # Try to resolve the feed URL
            resolved = await try_resolve_feed(client, slug, platform=platform, timeout=timeout)

            record: dict[str, Any] = {
                "name": name,
                "slug": slug,
                "website": company_data.get("website"),
                "industry": company_data.get("industry"),
                "discovery_source": "seed",
            }

            if resolved and resolved.status == "ok":
                record["feed_url"] = resolved.url
                record["feed_platform"] = resolved.platform
                record["feed_status"] = "active"
                with_feeds += 1
                logger.info("Seed company %s: feed resolved via %s", name, resolved.platform)
            else:
                record["feed_status"] = "no_feed"
                logger.info("Seed company %s: no feed found (slug=%r, platform=%r)", name, slug, platform)

            upsert_company(conn, record)
            conn.commit()

    finish_discovery_run(conn, run_id, companies_found=found, companies_with_feeds=with_feeds)
    conn.commit()

    logger.info(
        "Seed discovery complete: %d companies processed, %d with active feeds",
        found,
        with_feeds,
    )
    return with_feeds
