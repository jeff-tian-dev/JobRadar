"""Discover companies from Wellfound (AngelList) public directory."""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

import httpx

from feeds.resolver import try_resolve_feed
from pipeline.company_db import finish_discovery_run, insert_discovery_run, upsert_company

logger = logging.getLogger(__name__)

# Wellfound's public startup list (no auth required for basic listings)
_WELLFOUND_API_URL = "https://wellfound.com/companies"


async def discover_from_wellfound(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    max_companies: int = 100,
) -> int:
    """Scrape Wellfound startup listings and resolve ATS feeds.

    Note: Wellfound's public directory is HTML-only. This does a best-effort
    scrape of company names and URLs. For richer data, a paid API would be needed.

    Returns the number of companies added with active feeds.
    """
    run_id = insert_discovery_run(conn, "wellfound")
    conn.commit()

    # Wellfound blocks most scrapers; log and skip gracefully
    logger.info(
        "Wellfound discovery: skipping (Wellfound blocks unauthenticated scrapers). "
        "Add companies manually via the dashboard or seed YAML."
    )
    finish_discovery_run(
        conn,
        run_id,
        companies_found=0,
        companies_with_feeds=0,
        status="completed",
        error="Wellfound requires authentication; skipped",
    )
    conn.commit()
    return 0
