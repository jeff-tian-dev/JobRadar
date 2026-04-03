"""Discover companies from GitHub trending repositories."""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Any

import httpx

from feeds.resolver import try_resolve_feed
from pipeline.company_db import finish_discovery_run, insert_discovery_run, upsert_company

logger = logging.getLogger(__name__)

_GITHUB_TRENDING_URL = "https://github.com/trending"
_GITHUB_API_ORG_URL = "https://api.github.com/orgs/{org}"
_GITHUB_API_REPO_URL = "https://api.github.com/repos/{owner}/{repo}"


def _extract_trending_repos(html: str) -> list[tuple[str, str]]:
    """Extract (owner, repo) pairs from GitHub trending page HTML."""
    # Pattern: <h2 class="h3 lh-condensed"><a href="/owner/repo">
    pattern = re.compile(r'href="/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)"[^>]*>\s*<[^>]*>',  re.MULTILINE)
    seen: set[tuple[str, str]] = set()
    results: list[tuple[str, str]] = []
    for m in pattern.finditer(html):
        owner, repo = m.group(1), m.group(2)
        key = (owner, repo)
        if key not in seen and owner.lower() not in ("trending", "explore", "topics"):
            seen.add(key)
            results.append(key)
    return results[:30]  # limit to top 30


async def _get_org_website(client: httpx.AsyncClient, org: str) -> str | None:
    """Fetch GitHub org profile to get their website URL."""
    try:
        r = await client.get(
            _GITHUB_API_ORG_URL.format(org=org),
            headers={"Accept": "application/vnd.github+json"},
            timeout=10.0,
        )
        if r.status_code == 200:
            data = r.json()
            return data.get("blog") or data.get("html_url")
    except Exception as e:
        logger.debug("Failed to get org info for %s: %s", org, e)
    return None


async def discover_from_github(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    max_companies: int = 30,
) -> int:
    """Fetch GitHub trending, extract orgs, resolve their ATS feeds.

    Returns the number of companies added with active feeds.
    """
    run_id = insert_discovery_run(conn, "github")
    conn.commit()

    feed_cfg = settings.get("feeds", {})
    feed_timeout = float(feed_cfg.get("fetch_timeout_seconds", 15.0))
    found = 0
    with_feeds = 0

    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                _GITHUB_TRENDING_URL,
                headers={"Accept": "text/html"},
                timeout=20.0,
            )
            r.raise_for_status()
            repos = _extract_trending_repos(r.text)
        except Exception as e:
            logger.warning("Failed to fetch GitHub trending: %s", e)
            finish_discovery_run(conn, run_id, 0, 0, status="failed", error=str(e))
            conn.commit()
            return 0

        logger.info("Found %d trending repos on GitHub", len(repos))
        seen_orgs: set[str] = set()

        for owner, repo in repos[:max_companies]:
            if owner in seen_orgs:
                continue
            seen_orgs.add(owner)
            found += 1

            website = await _get_org_website(client, owner)

            slug_from_website = None
            if website and "github.com" not in website:
                m = re.search(r"https?://(?:www\.)?([^/]+)", website)
                if m:
                    slug_from_website = m.group(1).split(".")[0]

            slug = slug_from_website or owner

            resolved = await try_resolve_feed(client, slug, timeout=feed_timeout)

            record: dict[str, Any] = {
                "name": owner,
                "slug": slug,
                "website": website,
                "discovery_source": "github",
                "description": f"GitHub org behind trending repo: {owner}/{repo}",
            }

            if resolved and resolved.status == "ok":
                record["feed_url"] = resolved.url
                record["feed_platform"] = resolved.platform
                record["feed_status"] = "active"
                with_feeds += 1
                logger.info("GitHub org %s: feed resolved", owner)
            else:
                record["feed_status"] = "no_feed"

            upsert_company(conn, record)
            conn.commit()

    finish_discovery_run(conn, run_id, companies_found=found, companies_with_feeds=with_feeds)
    conn.commit()
    logger.info("GitHub discovery complete: %d orgs checked, %d with feeds", found, with_feeds)
    return with_feeds
