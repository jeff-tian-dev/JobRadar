"""Discover companies from Hacker News 'Who is Hiring' threads."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from typing import Any

import httpx
import ollama

from discovery.relevance import should_skip_company_for_relevance
from feeds.resolver import try_resolve_feed_with_website_fallback
from pipeline.company_db import (
    finish_discovery_run,
    insert_discovery_run,
    upsert_company,
)
from pipeline.config_paths import prompts_dir, read_ollama_repeat_penalty

logger = logging.getLogger(__name__)

_ALGOLIA_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?tags=ask_hn&query=who+is+hiring&hitsPerPage=5"
)
_HN_ITEMS_URL = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"


def _load_prompt() -> str:
    """Load the HN comment parser prompt."""
    path = prompts_dir() / "hn_parser.txt"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    # Fallback if prompt file not yet present
    return (
        "Extract company name, website URL, and location from this HN job posting comment. "
        "Return ONLY valid JSON: "
        '{"company_name": "<string>", "website": "<string or null>", '
        '"location": "<string or null>", "skip": false}. '
        'If not a job posting, return {"skip": true}.'
    )


def _parse_comment_with_llm(
    comment_text: str,
    settings: dict[str, Any],
) -> dict[str, Any] | None:
    """Use local Ollama to extract structured data from an HN hiring comment.

    Returns a dict with company_name, website, location, etc., or None on failure.
    """
    prompt = _load_prompt()
    model = settings.get("ollama_model", "qwen3:14b")
    host = settings.get("ollama_host", "http://127.0.0.1:11434")
    timeout = float(settings.get("ollama_timeout_seconds", 30))

    try:
        client = ollama.Client(host=host)
        response = client.chat(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": comment_text[:4000]},  # cap length
            ],
            format="json",
            options={
                "temperature": 0.1,
                "repeat_penalty": read_ollama_repeat_penalty(settings),
            },
        )
        raw = response["message"]["content"]
        data = json.loads(raw)
        if data.get("skip"):
            return None
        return data
    except Exception as e:
        logger.debug("LLM parse failed for HN comment: %s", e)
        return None


async def _get_latest_hiring_thread_id(client: httpx.AsyncClient) -> int | None:
    """Find the most recent 'Ask HN: Who is hiring?' thread via Algolia API."""
    try:
        r = await client.get(_ALGOLIA_URL, timeout=15.0)
        r.raise_for_status()
        hits = r.json().get("hits", [])
        for hit in hits:
            title = hit.get("title", "").lower()
            if "who is hiring" in title:
                return int(hit["objectID"])
    except Exception as e:
        logger.warning("Failed to find HN hiring thread: %s", e)
    return None


async def _get_thread_comments(client: httpx.AsyncClient, thread_id: int) -> list[str]:
    """Fetch top-level comments from an HN thread."""
    try:
        r = await client.get(_HN_ITEMS_URL.format(item_id=thread_id), timeout=15.0)
        r.raise_for_status()
        thread = r.json()
        kid_ids = thread.get("kids", [])[:50]  # limit to first 50 comments

        comments: list[str] = []
        for kid_id in kid_ids:
            try:
                rc = await client.get(_HN_ITEMS_URL.format(item_id=kid_id), timeout=10.0)
                rc.raise_for_status()
                item = rc.json()
                text = item.get("text", "") or ""
                if text and not item.get("deleted") and not item.get("dead"):
                    comments.append(text)
            except Exception as e:
                logger.debug("Failed to fetch HN comment %s: %s", kid_id, e)
                continue
        return comments
    except Exception as e:
        logger.warning("Failed to fetch HN thread %s: %s", thread_id, e)
        return []


async def discover_from_hn(
    conn: sqlite3.Connection,
    settings: dict[str, Any],
    profile: dict[str, Any] | None = None,
    max_companies: int | None = 100,
) -> int:
    """Parse the latest HN 'Who is Hiring' thread and add companies to the DB.

    Returns the number of companies added with active feeds.
    """
    run_id = insert_discovery_run(conn, "hn_hiring")
    conn.commit()

    found = 0
    with_feeds = 0
    feed_cfg = settings.get("feeds", {})
    feed_timeout = float(feed_cfg.get("fetch_timeout_seconds", 15.0))

    async with httpx.AsyncClient() as client:
        thread_id = await _get_latest_hiring_thread_id(client)
        if thread_id is None:
            logger.warning("Could not find HN hiring thread; skipping")
            finish_discovery_run(conn, run_id, 0, 0, status="failed", error="Thread not found")
            conn.commit()
            return 0

        logger.info("Found HN hiring thread: %s", thread_id)
        comments = await _get_thread_comments(client, thread_id)
        logger.info("Fetched %d comments from HN thread", len(comments))

        to_scan = comments if max_companies is None else comments[:max_companies]
        for comment in to_scan:
            parsed = _parse_comment_with_llm(comment, settings)
            if not parsed:
                continue

            company_name = parsed.get("company_name", "").strip()
            if not company_name:
                continue

            website = parsed.get("website") or None
            location = parsed.get("location") or None
            desc = parsed.get("description")
            if isinstance(desc, str):
                desc_val: str | None = desc
            else:
                desc_val = None

            if should_skip_company_for_relevance(
                company_name, desc_val, None, profile, settings
            ):
                continue

            found += 1

            # Try to find a slug from the website URL
            slug: str | None = None
            if website:
                m = re.search(r"https?://(?:www\.)?([^/]+)", website)
                if m:
                    slug = m.group(1).split(".")[0]

            resolved = None
            if slug:
                w = website.strip() if isinstance(website, str) else ""
                resolved = await try_resolve_feed_with_website_fallback(
                    client,
                    slug,
                    website=w or None,
                    timeout=feed_timeout,
                )

            record: dict[str, Any] = {
                "name": company_name,
                "slug": slug,
                "website": website,
                "location": location,
                "discovery_source": "hn_hiring",
                "description": desc_val,
            }

            if resolved and resolved.status == "ok":
                record["feed_url"] = resolved.url
                record["feed_platform"] = resolved.platform
                record["feed_status"] = "active"
                with_feeds += 1
                logger.info("HN company %s: feed resolved", company_name)
            else:
                record["feed_status"] = "no_feed"

            upsert_company(conn, record)
            conn.commit()

    finish_discovery_run(conn, run_id, companies_found=found, companies_with_feeds=with_feeds)
    conn.commit()
    logger.info("HN discovery complete: %d found, %d with feeds", found, with_feeds)
    return with_feeds
