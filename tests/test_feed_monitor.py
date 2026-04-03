"""Tests for feeds/monitor.py (mocked HTTP and DB)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feeds.monitor import fetch_all_active_feeds, fetch_feed
from pipeline.company_db import upsert_company
from pipeline.models import RawListing

_FIXTURES = Path(__file__).parent / "fixtures"
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = (_REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    migration = (_REPO_ROOT / "db" / "migrations" / "001_add_companies.sql").read_text(
        encoding="utf-8"
    )
    try:
        conn.executescript(migration)
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise
    conn.commit()
    return conn


def _greenhouse_xml() -> str:
    return (_FIXTURES / "sample_greenhouse.xml").read_text(encoding="utf-8")


def _lever_xml() -> str:
    return (_FIXTURES / "sample_lever.xml").read_text(encoding="utf-8")


def _greenhouse_json() -> str:
    """Simulate a Greenhouse JSON API response."""
    import json
    return json.dumps({
        "jobs": [
            {
                "title": "Senior Software Engineer, Payments",
                "absolute_url": "https://job-boards.greenhouse.io/stripe/jobs/12345",
                "location": {"name": "San Francisco, CA"},
                "updated_at": "2025-01-01T00:00:00-05:00",
            },
            {
                "title": "Staff Engineer, Infrastructure",
                "absolute_url": "https://job-boards.greenhouse.io/stripe/jobs/12346",
                "location": {"name": "New York, NY"},
                "updated_at": "2025-01-02T00:00:00-05:00",
            },
        ]
    })


def _ashby_xml() -> str:
    return (_FIXTURES / "sample_ashby.xml").read_text(encoding="utf-8")


# --- fetch_feed ---


@pytest.mark.asyncio
async def test_fetch_feed_returns_raw_listings() -> None:
    conn = _make_conn()
    cid = upsert_company(
        conn,
        {
            "name": "Stripe",
            "slug": "stripe",
            "feed_url": "https://api.greenhouse.io/v1/boards/stripe/jobs",
            "feed_platform": "greenhouse",
            "feed_status": "active",
            "discovery_source": "seed",
        },
    )
    conn.commit()

    company_row = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,)).fetchone()

    board_payload = json.loads(_greenhouse_json())

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.headers = {"content-type": "application/json"}
        if re.search(r"/boards/[^/]+/jobs/\d+$", url):
            job_id = url.rstrip("/").split("/")[-1]
            body = {
                "content": f"<p>Description for job {job_id} with details.</p>",
            }
            resp.text = json.dumps(body)
            resp.json = MagicMock(return_value=body)
        else:
            resp.text = _greenhouse_json()
            resp.json = MagicMock(return_value=board_payload)
        return resp

    mock_client = MagicMock()
    mock_client.get = mock_get

    listings = await fetch_feed(mock_client, company_row)
    assert len(listings) == 2
    for listing in listings:
        assert isinstance(listing, RawListing)
        assert listing.company == "Stripe"
        assert listing.source == "greenhouse"
        assert listing.source_url.startswith("https://")
        assert listing.title
        assert "Description for job" in listing.description
        assert isinstance(listing.scraped_at, datetime)


# --- fetch_all_active_feeds ---


@pytest.mark.asyncio
async def test_fetch_all_active_feeds_collects_from_all_companies() -> None:
    import json as _json
    conn = _make_conn()
    upsert_company(
        conn,
        {
            "name": "Stripe",
            "slug": "stripe",
            "feed_url": "https://api.greenhouse.io/v1/boards/stripe/jobs",
            "feed_platform": "greenhouse",
            "feed_status": "active",
            "discovery_source": "seed",
        },
    )
    upsert_company(
        conn,
        {
            "name": "Linear",
            "slug": "linear",
            "feed_url": "https://jobs.ashbyhq.com/linear.rss",
            "feed_platform": "ashby",
            "feed_status": "active",
            "discovery_source": "seed",
        },
    )
    conn.commit()

    greenhouse_json_str = _greenhouse_json()
    ashby_xml = _ashby_xml()

    board_data = _json.loads(greenhouse_json_str)

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        if "api.greenhouse.io" in url and re.search(r"/boards/[^/]+/jobs/\d+$", url):
            job_id = url.rstrip("/").split("/")[-1]
            detail = {"content": f"<p>GH detail {job_id}</p>"}
            resp.headers = {"content-type": "application/json"}
            resp.text = _json.dumps(detail)
            resp.json = MagicMock(return_value=detail)
        elif "greenhouse" in url or "api.greenhouse" in url:
            resp.headers = {"content-type": "application/json"}
            resp.text = greenhouse_json_str
            resp.json = MagicMock(return_value=board_data)
        else:
            resp.headers = {"content-type": "application/atom+xml"}
            resp.text = ashby_xml
            resp.json = MagicMock(side_effect=Exception("not json"))
        return resp

    mock_client_instance = MagicMock()
    mock_client_instance.get = mock_get
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("feeds.monitor.httpx.AsyncClient", return_value=mock_client_instance):
        with patch("feeds.monitor.asyncio.sleep", new_callable=AsyncMock):
            listings = await fetch_all_active_feeds(conn)

    # Stripe (greenhouse JSON) has 2 entries, Linear (ashby RSS) has 2 entries
    assert len(listings) == 4
    companies = {l.company for l in listings}
    assert "Stripe" in companies
    assert "Linear" in companies


@pytest.mark.asyncio
async def test_fetch_all_active_feeds_skips_failed_and_continues() -> None:
    import json as _json
    conn = _make_conn()
    upsert_company(
        conn,
        {
            "name": "Good Co",
            "slug": "goodco",
            "feed_url": "https://jobs.ashbyhq.com/goodco.rss",
            "feed_platform": "ashby",
            "feed_status": "active",
            "discovery_source": "seed",
        },
    )
    upsert_company(
        conn,
        {
            "name": "Bad Co",
            "slug": "badco",
            "feed_url": "https://jobs.ashbyhq.com/badco.rss",
            "feed_platform": "ashby",
            "feed_status": "active",
            "discovery_source": "seed",
        },
    )
    conn.commit()

    ashby_xml = _ashby_xml()

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        if "badco" in url:
            raise Exception("Connection refused")
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.headers = {"content-type": "application/atom+xml"}
        resp.text = ashby_xml
        return resp

    mock_client_instance = MagicMock()
    mock_client_instance.get = mock_get
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("feeds.monitor.httpx.AsyncClient", return_value=mock_client_instance):
        with patch("feeds.monitor.asyncio.sleep", new_callable=AsyncMock):
            listings = await fetch_all_active_feeds(conn)

    # Only goodco's 2 entries returned; badco skipped
    assert len(listings) == 2
    assert all(l.company == "Good Co" for l in listings)


@pytest.mark.asyncio
async def test_fetch_all_active_feeds_empty_when_no_companies() -> None:
    conn = _make_conn()
    listings = await fetch_all_active_feeds(conn)
    assert listings == []


@pytest.mark.asyncio
async def test_fetch_all_active_feeds_marks_broken_after_max_failures() -> None:
    conn = _make_conn()
    cid = upsert_company(
        conn,
        {
            "name": "Flaky Co",
            "slug": "flakyco",
            "feed_url": "https://boards.greenhouse.io/flakyco/feed",
            "feed_platform": "greenhouse",
            "feed_status": "active",
            "discovery_source": "seed",
            "consecutive_failures": 4,  # One away from threshold (default=5)
        },
    )
    conn.commit()

    mock_client_instance = MagicMock()
    mock_client_instance.get = AsyncMock(side_effect=Exception("timeout"))
    mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
    mock_client_instance.__aexit__ = AsyncMock(return_value=False)

    with patch("feeds.monitor.httpx.AsyncClient", return_value=mock_client_instance):
        with patch("feeds.monitor.asyncio.sleep", new_callable=AsyncMock):
            await fetch_all_active_feeds(conn)

    row = conn.execute("SELECT feed_status FROM companies WHERE id = ?", (cid,)).fetchone()
    assert row["feed_status"] == "broken"
