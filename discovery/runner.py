"""Orchestrate all discovery sources, resolve feeds, update the companies table."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from discovery.relevance import score_company_relevance
from discovery.sources.github_trending import discover_from_github
from discovery.sources.hn_hiring import discover_from_hn
from discovery.sources.seed import discover_from_seed
from discovery.sources.wellfound import discover_from_wellfound
from discovery.sources.yc import discover_from_yc

logger = logging.getLogger(__name__)

_ALL_SOURCES = ["seed", "hn_hiring", "yc", "github", "wellfound"]


async def run_discovery(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    profile: dict[str, Any] | None = None,
    sources: list[str] | None = None,
) -> dict[str, int]:
    """Run company discovery from configured sources.

    Args:
        conn: Open SQLite connection.
        settings: Loaded settings dict.
        profile: Candidate profile dict (used for relevance filtering if enabled).
        sources: List of source names to run. Defaults to all configured sources.

    Returns:
        Dict mapping source name → number of companies added with active feeds.
    """
    disc_cfg = settings.get("discovery", {})
    source_cfg = disc_cfg.get("sources", {})

    # Determine which sources to run
    if sources is None:
        sources = [s for s in _ALL_SOURCES if source_cfg.get(s, False)]
    if not sources:
        logger.info("No discovery sources enabled; add sources to settings.yaml discovery.sources")
        return {}

    logger.info("Running discovery for sources: %s", sources)
    results: dict[str, int] = {}

    for source in sources:
        logger.info("=== Discovery source: %s ===", source)
        try:
            if source == "seed":
                count = await discover_from_seed(conn, settings)
            elif source == "hn_hiring":
                count = await discover_from_hn(conn, settings)
            elif source == "yc":
                count = await discover_from_yc(conn, settings)
            elif source == "github":
                count = await discover_from_github(conn, settings)
            elif source == "wellfound":
                count = await discover_from_wellfound(conn, settings)
            else:
                logger.warning("Unknown discovery source: %s", source)
                count = 0
            results[source] = count
        except Exception:
            logger.exception("Discovery source %s failed", source)
            results[source] = 0

    total = sum(results.values())
    logger.info(
        "Discovery complete. Sources: %s. Total new feeds: %d",
        results,
        total,
    )
    return results
