"""Tests for feeds/resolver.py (mocked HTTP)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from feeds.resolver import (
    FEED_URL_PATTERNS,
    ResolvedFeed,
    detect_platform_from_url,
    try_resolve_feed,
    verify_feed_url,
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _greenhouse_xml() -> str:
    return (_FIXTURES / "sample_greenhouse.xml").read_text(encoding="utf-8")


def _lever_xml() -> str:
    return (_FIXTURES / "sample_lever.xml").read_text(encoding="utf-8")


# --- detect_platform_from_url ---


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://boards.greenhouse.io/stripe/jobs", "greenhouse"),
        ("https://jobs.lever.co/vercel/abc", "lever"),
        ("https://jobs.ashby.io/linear/jobs", "ashby"),
        ("https://ashbyhq.com/linear", "ashby"),
        ("https://apply.workable.com/render", "workable"),
        ("https://stripe.com/careers", None),
        ("https://example.com", None),
    ],
)
def test_detect_platform_from_url(url: str, expected: str | None) -> None:
    assert detect_platform_from_url(url) == expected


# --- FEED_URL_PATTERNS ---


def test_feed_url_patterns_contain_all_platforms() -> None:
    for platform in ("greenhouse", "lever", "ashby", "workable"):
        assert platform in FEED_URL_PATTERNS
        url = FEED_URL_PATTERNS[platform].format(slug="testco")
        assert "testco" in url


# --- verify_feed_url ---


@pytest.mark.asyncio
async def test_verify_feed_url_ashby_json() -> None:
    import json as _json
    ashby_data = {"jobPostings": [{"title": "Engineer"}, {"title": "Designer"}]}
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}
    mock_response.text = _json.dumps(ashby_data)
    mock_response.json = MagicMock(return_value=ashby_data)
    mock_response.url = "https://api.ashbyhq.com/posting-api/job-board/linear"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    is_valid, count = await verify_feed_url(mock_client, "https://api.ashbyhq.com/posting-api/job-board/linear")
    assert is_valid is True
    assert count == 2


@pytest.mark.asyncio
async def test_verify_feed_url_valid() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/rss+xml"}
    mock_response.text = _greenhouse_xml()
    mock_response.url = "https://boards.greenhouse.io/stripe/feed"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    is_valid, count = await verify_feed_url(mock_client, "https://boards.greenhouse.io/stripe/feed")
    assert is_valid is True
    assert count == 2


@pytest.mark.asyncio
async def test_verify_feed_url_404_returns_false() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {}
    mock_response.text = ""
    mock_response.url = "https://boards.greenhouse.io/notexist/feed"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    is_valid, count = await verify_feed_url(
        mock_client, "https://boards.greenhouse.io/notexist/feed"
    )
    assert is_valid is False
    assert count == 0


@pytest.mark.asyncio
async def test_verify_feed_url_exception_returns_false() -> None:
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("network error"))

    is_valid, count = await verify_feed_url(mock_client, "https://example.com/feed")
    assert is_valid is False
    assert count == 0


# --- try_resolve_feed ---


@pytest.mark.asyncio
async def test_try_resolve_feed_specific_platform() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/rss+xml"}
    mock_response.text = _greenhouse_xml()
    mock_response.url = "https://boards.greenhouse.io/stripe/feed"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await try_resolve_feed(mock_client, "stripe", platform="greenhouse")
    assert result is not None
    assert result.platform == "greenhouse"
    assert "stripe" in result.url
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_try_resolve_feed_tries_all_platforms_returns_first_match() -> None:
    """When platform is None, try all platforms and return the first that works.
    Greenhouse is first in FEED_URL_PATTERNS, so a working Greenhouse feed returns on call 1.
    """
    import json as _json

    greenhouse_json = _json.dumps({
        "jobs": [
            {"title": "Software Engineer", "absolute_url": "https://job-boards.greenhouse.io/co/jobs/1", "location": {"name": "Remote"}, "updated_at": "2025-01-01T00:00:00Z"},
        ]
    })

    call_count = 0

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        mock_resp = MagicMock()
        mock_resp.url = url
        if "greenhouse" in url:
            mock_resp.status_code = 200
            mock_resp.headers = {"content-type": "application/json"}
            mock_resp.text = greenhouse_json
            mock_resp.json = MagicMock(return_value=_json.loads(greenhouse_json))
        else:
            mock_resp.status_code = 404
            mock_resp.headers = {}
            mock_resp.text = ""
        return mock_resp

    mock_client = MagicMock()
    mock_client.get = mock_get

    result = await try_resolve_feed(mock_client, "testco")
    assert result is not None
    assert result.platform == "greenhouse"
    # Greenhouse is first in FEED_URL_PATTERNS, so only 1 call needed
    assert call_count == 1


@pytest.mark.asyncio
async def test_try_resolve_feed_returns_none_when_all_fail() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.headers = {}
    mock_response.text = ""
    mock_response.url = "https://example.com"

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    result = await try_resolve_feed(mock_client, "notacompany")
    assert result is None
