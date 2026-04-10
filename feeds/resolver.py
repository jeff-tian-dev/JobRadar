"""Resolve a company slug + platform into a verified RSS feed URL."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import feedparser
import httpx

logger = logging.getLogger(__name__)

FEED_URL_PATTERNS: dict[str, str] = {
    # Greenhouse: public JSON API
    "greenhouse": "https://api.greenhouse.io/v1/boards/{slug}/jobs",
    # Lever: public JSON API (returns array of postings)
    "lever": "https://api.lever.co/v0/postings/{slug}?mode=json",
    # Ashby: internal posting API used by their React frontend (returns {"jobPostings": [...]})
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    # Workable: public RSS at apply.workable.com/{slug}/rss
    "workable": "https://apply.workable.com/{slug}/rss",
}

# Patterns to detect ATS platform from a URL
_PLATFORM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ashby", re.compile(r"ashbyhq\.com|jobs\.ashby\.io", re.IGNORECASE)),
    ("greenhouse", re.compile(r"greenhouse\.io", re.IGNORECASE)),
    ("lever", re.compile(r"jobs\.lever\.co|lever\.co", re.IGNORECASE)),
    ("workable", re.compile(r"apply\.workable\.com|jobs\.workable\.com", re.IGNORECASE)),
]


@dataclass(frozen=True)
class ResolvedFeed:
    """Result of attempting to resolve a feed URL for a company."""

    platform: str
    url: str
    status: str       # ok | not_found | error
    entry_count: int  # 0 if not ok


def detect_platform_from_url(url: str) -> str | None:
    """Return the ATS platform name if the URL matches a known pattern, else None."""
    for platform, pattern in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return platform
    return None


async def verify_feed_url(
    client: httpx.AsyncClient,
    url: str,
    timeout: float = 15.0,
) -> tuple[bool, int]:
    """Fetch a feed URL and verify it returns valid RSS/JSON with entries.

    Handles both RSS/Atom (Ashby, Workable) and JSON APIs (Greenhouse, Lever).
    Returns (is_valid, entry_count).
    """
    try:
        r = await client.get(url, timeout=timeout, follow_redirects=True)
        if r.status_code != 200:
            return False, 0
        content_type = r.headers.get("content-type", "")

        # JSON API response (Greenhouse, Lever, Ashby)
        if "json" in content_type or url.startswith("https://api.ashbyhq.com"):
            try:
                data = r.json()
                # Greenhouse: {"jobs": [...]}
                if isinstance(data, dict) and "jobs" in data:
                    return True, len(data["jobs"])
                # Ashby: {"jobPostings": [...]}
                if isinstance(data, dict) and "jobPostings" in data:
                    return True, len(data["jobPostings"])
                # Lever: [{"text": "...", ...}]
                if isinstance(data, list):
                    return True, len(data)
            except Exception:
                pass
            return False, 0

        # RSS/Atom feed
        feed = feedparser.parse(r.text)
        entries = feed.get("entries", [])
        has_title = bool(feed.feed.get("title"))
        return (has_title or len(entries) > 0), len(entries)
    except Exception as e:
        logger.debug("Feed verification failed for %s: %s", url, e)
        return False, 0


async def try_resolve_feed(
    client: httpx.AsyncClient,
    slug: str,
    platform: str | None = None,
    timeout: float = 15.0,
) -> ResolvedFeed | None:
    """Try to find a working RSS feed URL for the given company slug.

    If platform is given, tries only that platform.
    If platform is None, tries all known platforms in order.

    Returns the first working ResolvedFeed, or None if nothing works.
    """
    platforms_to_try = [platform] if platform else list(FEED_URL_PATTERNS.keys())

    for p in platforms_to_try:
        url = FEED_URL_PATTERNS[p].format(slug=slug)
        is_valid, entry_count = await verify_feed_url(client, url, timeout=timeout)
        if is_valid:
            logger.info("Resolved feed for %r via %s: %s (%d entries)", slug, p, url, entry_count)
            return ResolvedFeed(platform=p, url=url, status="ok", entry_count=entry_count)
        logger.debug("No feed at %s (platform=%s)", url, p)

    return None


async def try_resolve_feed_with_website_fallback(
    client: httpx.AsyncClient,
    slug: str,
    *,
    platform: str | None = None,
    website: str | None = None,
    timeout: float = 15.0,
) -> ResolvedFeed | None:
    """Resolve feed by slug; if that fails, fetch ``website`` and retry with inferred ATS platform."""
    resolved = await try_resolve_feed(client, slug, platform=platform, timeout=timeout)
    if resolved is not None:
        return resolved
    site = (website or "").strip()
    if not site:
        return None
    inferred = await detect_platform_from_careers_page(client, site, timeout=timeout)
    if inferred is None:
        return None
    return await try_resolve_feed(client, slug, platform=inferred, timeout=timeout)


async def detect_platform_from_careers_page(
    client: httpx.AsyncClient,
    careers_url: str,
    timeout: float = 15.0,
) -> str | None:
    """Fetch a careers page and detect if it's hosted on a known ATS platform.

    Returns the platform name or None.
    """
    # First check the URL itself
    platform = detect_platform_from_url(careers_url)
    if platform:
        return platform

    # Fetch the page and look for ATS platform links/redirects
    try:
        r = await client.get(careers_url, timeout=timeout, follow_redirects=True)
        # Check final URL after redirects
        platform = detect_platform_from_url(str(r.url))
        if platform:
            return platform
        # Scan page content for ATS platform domain references
        for p, pattern in _PLATFORM_PATTERNS:
            if pattern.search(r.text):
                return p
        # Also look for ashbyhq.com specifically in page content
        if "ashbyhq.com" in r.text:
            return "ashby"
    except Exception as e:
        logger.debug("Failed to fetch careers page %s: %s", careers_url, e)

    return None
