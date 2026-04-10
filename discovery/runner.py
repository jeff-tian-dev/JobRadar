"""Orchestrate all discovery sources, resolve feeds, update the companies table."""

from __future__ import annotations

import logging
import sqlite3
from typing import Any

from discovery.settings import (
    discovery_enabled,
    enabled_discovery_sources,
    max_companies_per_source,
)
from discovery.sources.github_trending import discover_from_github
from discovery.sources.hn_hiring import discover_from_hn
from discovery.sources.seed import discover_from_seed
from discovery.sources.wellfound import discover_from_wellfound
from discovery.sources.yc import discover_from_yc

logger = logging.getLogger(__name__)


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
    if isinstance(disc_cfg, dict) and not discovery_enabled(settings):
        logger.info("Discovery disabled (discovery.enabled: false)")
        return {}

    source_cfg = disc_cfg.get("sources", {}) if isinstance(disc_cfg, dict) else {}
    if not isinstance(source_cfg, dict):
        source_cfg = {}

    max_c = max_companies_per_source(settings)

    # Determine which sources to run
    if sources is None:
        sources = enabled_discovery_sources(source_cfg)
    if not sources:
        logger.info("No discovery sources enabled; add sources to settings.yaml discovery.sources")
        return {}

    logger.info("Running discovery for sources: %s", sources)
    results: dict[str, int] = {}

    for source in sources:
        logger.info("=== Discovery source: %s ===", source)
        try:
            if source == "seed":
                count = await discover_from_seed(conn, settings, max_companies=max_c)
            elif source == "hn_hiring":
                count = await discover_from_hn(
                    conn, settings, profile=profile, max_companies=max_c
                )
            elif source == "yc":
                count = await discover_from_yc(
                    conn, settings, profile=profile, max_companies=max_c
                )
            elif source == "github":
                count = await discover_from_github(
                    conn, settings, profile=profile, max_companies=max_c
                )
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
