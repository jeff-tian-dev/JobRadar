"""Parse RSS/Atom XML and JSON from ATS platforms into FeedEntry objects."""

from __future__ import annotations

import html as html_stdlib
import logging
import re
from dataclasses import dataclass
from typing import Any

import feedparser

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")

# Greenhouse board list JSON omits full descriptions; detail is on per-job API URLs.
_GREENHOUSE_LISTING_URL_RE = re.compile(
    r"https?://(?:job-boards|boards)\.greenhouse\.io/([^/]+)/jobs/(\d+)(?:\?[^#]*)?/?$",
    re.IGNORECASE,
)


def parse_greenhouse_listing_url(url: str) -> tuple[str, str] | None:
    """Parse board slug and job id from a public Greenhouse job URL, if it matches."""
    if not url:
        return None
    m = _GREENHOUSE_LISTING_URL_RE.match(url.strip())
    if not m:
        return None
    return m.group(1), m.group(2)


def greenhouse_job_detail_api_url(board_slug: str, job_id: str) -> str:
    """Public JSON URL for a single Greenhouse posting (includes HTML content)."""
    return f"https://api.greenhouse.io/v1/boards/{board_slug}/jobs/{job_id}"


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    text = html_stdlib.unescape(html or "")
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_html_to_plain(html: str) -> str:
    """Public helper: HTML entities + tags stripped to plain text."""
    return _strip_html(html)


@dataclass(frozen=True)
class FeedEntry:
    """Single parsed feed entry before conversion to RawListing."""

    title: str
    url: str
    company: str
    location: str
    description: str
    published: str | None


def _get_content(entry: object) -> str:
    """Extract the best available content from a feedparser entry."""
    # feedparser normalizes these attributes
    content_list = getattr(entry, "content", None)
    if content_list:
        return content_list[0].get("value", "")
    summary = getattr(entry, "summary", None)
    if summary:
        return summary
    description = getattr(entry, "description", None)
    if description:
        return description
    return ""


def _extract_location_from_title(title: str) -> tuple[str, str]:
    """For Lever feeds, location is often a suffix: 'Engineer - San Francisco, CA'.

    Returns (cleaned_title, location).
    """
    # Match " - Location" or " | Location" at end of title
    match = re.search(r"\s+[-|]\s+([^-|]+)$", title)
    if match:
        loc = match.group(1).strip()
        # Heuristic: if the suffix contains a comma or "remote" it's a location
        if "," in loc or re.search(r"\bremote\b", loc, re.IGNORECASE):
            clean_title = title[: match.start()].strip()
            return clean_title, loc
    return title, ""


def parse_greenhouse_json(data: dict[str, Any], company_name: str) -> list[FeedEntry]:
    """Parse Greenhouse JSON API response into FeedEntry objects.

    Greenhouse API: GET https://api.greenhouse.io/v1/boards/{slug}/jobs
    Response: {"jobs": [{"title", "absolute_url", "location": {"name"}, "updated_at"}, ...]}
    """
    entries: list[FeedEntry] = []
    for job in data.get("jobs", []):
        try:
            title = job.get("title", "").strip()
            url = job.get("absolute_url", "").strip()
            location = (job.get("location") or {}).get("name", "")
            published = job.get("updated_at") or job.get("first_published")
            if not title or not url:
                continue
            raw_content = job.get("content") or ""
            if raw_content:
                description = _strip_html(raw_content)[:5000]
            else:
                description = ""
            entries.append(
                FeedEntry(
                    title=title,
                    url=url,
                    company=company_name,
                    location=location or "",
                    description=description,
                    published=published,
                )
            )
        except Exception:
            logger.exception("Failed to parse Greenhouse job entry for %s", company_name)
            continue
    return entries


def parse_lever_json(data: list[dict[str, Any]], company_name: str) -> list[FeedEntry]:
    """Parse Lever JSON API response into FeedEntry objects.

    Lever API: GET https://api.lever.co/v0/postings/{slug}?mode=json
    Response: [{"text": title, "hostedUrl": url, "categories": {"location"}, ...}]
    """
    entries: list[FeedEntry] = []
    for job in data:
        try:
            title = job.get("text", "").strip()
            url = job.get("hostedUrl", "").strip()
            cats = job.get("categories") or {}
            location = cats.get("location") or cats.get("team") or ""
            descr_html = job.get("descriptionPlain") or job.get("description") or ""
            description = _strip_html(descr_html) if "<" in descr_html else descr_html
            if not title or not url:
                continue
            entries.append(
                FeedEntry(
                    title=title,
                    url=url,
                    company=company_name,
                    location=location,
                    description=description[:5000],
                    published=None,
                )
            )
        except Exception:
            logger.exception("Failed to parse Lever job entry for %s", company_name)
            continue
    return entries


def parse_ashby_json(data: dict[str, Any], company_name: str) -> list[FeedEntry]:
    """Parse Ashby posting API response into FeedEntry objects.

    Ashby API: GET https://api.ashbyhq.com/posting-api/job-board/{slug}
    Response: {"jobPostings": [{"title", "jobPostingUrl", "locationName",
                                "publishedDate", "descriptionHtml", ...}]}
    """
    entries: list[FeedEntry] = []
    for job in data.get("jobPostings", []):
        try:
            title = job.get("title", "").strip()
            url = job.get("jobPostingUrl", "").strip()
            if not title or not url:
                continue
            location = job.get("locationName") or ""
            published = job.get("publishedDate") or None
            descr_html = job.get("descriptionHtml") or ""
            description = _strip_html(descr_html) if descr_html else ""
            entries.append(
                FeedEntry(
                    title=title,
                    url=url,
                    company=company_name,
                    location=location,
                    description=description[:5000],
                    published=published,
                )
            )
        except Exception:
            logger.exception("Failed to parse Ashby job entry for %s", company_name)
            continue
    return entries


def parse_feed_xml(content: str, company_name: str, platform: str) -> list[FeedEntry]:
    """Parse RSS/Atom XML content into FeedEntry objects.

    Args:
        content: Raw XML string from the feed.
        company_name: Company name from the companies table (not the feed itself).
        platform: One of greenhouse | lever | ashby | workable.

    Returns:
        List of FeedEntry objects. Empty on parse failure (logged, not raised).
    """
    try:
        feed = feedparser.parse(content)
    except Exception:
        logger.exception("feedparser failed to parse feed for %s", company_name)
        return []

    entries: list[FeedEntry] = []
    for entry in feed.get("entries", []):
        try:
            title = getattr(entry, "title", "") or ""
            url = getattr(entry, "link", "") or ""
            raw_content = _get_content(entry)
            description = _strip_html(raw_content) if raw_content else ""

            # Published date
            published: str | None = None
            if hasattr(entry, "published"):
                published = str(entry.published)
            elif hasattr(entry, "updated"):
                published = str(entry.updated)

            # Location extraction
            location = ""
            if platform == "lever":
                title, location = _extract_location_from_title(title)

            entries.append(
                FeedEntry(
                    title=title.strip(),
                    url=url.strip(),
                    company=company_name,
                    location=location,
                    description=description,
                    published=published,
                )
            )
        except Exception:
            logger.exception(
                "Failed to parse feed entry for %s: %r",
                company_name,
                getattr(entry, "title", "<unknown>"),
            )
            continue

    return entries
