"""Tests for the discovery subsystem (mocked HTTP and LLM)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from discovery.relevance import score_company_relevance
from discovery.runner import run_discovery
from discovery.settings import enabled_discovery_sources
from discovery.sources.seed import discover_from_seed
from pipeline.company_db import get_active_feed_companies, iter_companies

_REPO_ROOT = Path(__file__).resolve().parents[1]
_FIXTURES = Path(__file__).parent / "fixtures"


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


def _minimal_settings() -> dict:
    return {
        "ollama_model": "test-model",
        "ollama_host": "http://127.0.0.1:11434",
        "ollama_timeout_seconds": 5,
        "feeds": {"fetch_timeout_seconds": 5},
        "discovery": {
            "relevance_threshold": 40,
            "sources": {"seed": True},
        },
    }


def _minimal_profile() -> dict:
    return {
        "name": "Test User",
        "summary": "Backend engineer with 8 years of experience.",
        "skills": {"expert": ["Python", "Go"], "proficient": [], "familiar": []},
        "preferences": {
            "target_titles": ["Senior Engineer"],
            "industries_preferred": ["developer tools"],
            "deal_breakers": [],
        },
        "alert_threshold": 78,
    }


# --- seed discovery ---


@pytest.mark.asyncio
async def test_discover_from_seed_populates_companies() -> None:
    """Seed discovery should insert companies with resolved feeds."""
    conn = _make_conn()

    greenhouse_xml = (_FIXTURES / "sample_greenhouse.xml").read_text(encoding="utf-8")

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.url = url
        if "greenhouse" in url:
            resp.status_code = 200
            resp.headers = {"content-type": "application/rss+xml"}
            resp.text = greenhouse_xml
        else:
            resp.status_code = 404
            resp.headers = {}
            resp.text = ""
        return resp

    mock_client = MagicMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("discovery.sources.seed.httpx.AsyncClient", return_value=mock_client):
        # Patch seed to only return a few known greenhouse companies
        seed_data = [
            {"name": "Stripe", "slug": "stripe", "platform": "greenhouse", "website": "https://stripe.com"},
            {"name": "Figma", "slug": "figma", "platform": "greenhouse", "website": "https://figma.com"},
        ]
        with patch("discovery.sources.seed.load_seed_companies", return_value=seed_data):
            count = await discover_from_seed(conn, _minimal_settings())

    # Both companies have greenhouse feeds → 2 with feeds
    assert count == 2
    active = get_active_feed_companies(conn)
    assert len(active) == 2
    names = {r["name"] for r in active}
    assert "Stripe" in names
    assert "Figma" in names


@pytest.mark.asyncio
async def test_discover_from_seed_handles_no_feed() -> None:
    """Companies with no working feed should be stored with feed_status=no_feed."""
    conn = _make_conn()

    async def mock_get(url: str, **kwargs: object) -> MagicMock:
        resp = MagicMock()
        resp.url = url
        resp.status_code = 404
        resp.headers = {}
        resp.text = ""
        return resp

    mock_client = MagicMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("discovery.sources.seed.httpx.AsyncClient", return_value=mock_client):
        seed_data = [{"name": "NoFeed Co", "slug": "nofeed", "platform": "greenhouse"}]
        with patch("discovery.sources.seed.load_seed_companies", return_value=seed_data):
            count = await discover_from_seed(conn, _minimal_settings())

    assert count == 0
    companies = list(iter_companies(conn))
    assert len(companies) == 1
    assert companies[0]["feed_status"] == "no_feed"


# --- relevance scoring ---


def test_score_company_relevance_returns_score_and_reason() -> None:
    """Mocked LLM returns a score and reason for a company."""
    mock_response = {
        "message": {"content": json.dumps({"relevant": True, "score": 82, "reason": "Strong fit."})}
    }
    mock_client = MagicMock()
    mock_client.chat = MagicMock(return_value=mock_response)

    with patch("discovery.relevance.ollama.Client", return_value=mock_client):
        score, reason = score_company_relevance(
            company_name="Stripe",
            company_description="Financial infrastructure for the internet.",
            industry="fintech",
            profile=_minimal_profile(),
            settings=_minimal_settings(),
        )

    assert score == 82
    assert reason == "Strong fit."


def test_score_company_relevance_returns_default_on_llm_failure() -> None:
    """Returns (50, 'LLM unavailable') when LLM call fails."""
    with patch("discovery.relevance.ollama.Client", side_effect=Exception("connection refused")):
        score, reason = score_company_relevance(
            company_name="Unknown Co",
            company_description=None,
            industry=None,
            profile=_minimal_profile(),
            settings=_minimal_settings(),
        )

    assert score == 50
    assert "unavailable" in reason.lower()


def test_score_company_relevance_clamps_to_0_100() -> None:
    """Score is clamped to valid 0-100 range even if LLM returns out-of-range."""
    mock_response = {
        "message": {"content": json.dumps({"relevant": True, "score": 150, "reason": "Very good."})}
    }
    mock_client = MagicMock()
    mock_client.chat = MagicMock(return_value=mock_response)

    with patch("discovery.relevance.ollama.Client", return_value=mock_client):
        score, _ = score_company_relevance(
            company_name="Test", company_description=None, industry=None,
            profile=_minimal_profile(), settings=_minimal_settings(),
        )

    assert score == 100


# --- run_discovery orchestration ---


@pytest.mark.asyncio
async def test_run_discovery_runs_only_specified_sources() -> None:
    """run_discovery with sources=['seed'] only calls seed discovery."""
    conn = _make_conn()

    with patch("discovery.runner.discover_from_seed", new_callable=AsyncMock, return_value=3) as mock_seed, \
         patch("discovery.runner.discover_from_hn", new_callable=AsyncMock, return_value=1) as mock_hn, \
         patch("discovery.runner.discover_from_yc", new_callable=AsyncMock, return_value=2) as mock_yc:

        results = await run_discovery(conn, _minimal_settings(), sources=["seed"])

    mock_seed.assert_called_once()
    mock_hn.assert_not_called()
    mock_yc.assert_not_called()
    assert results == {"seed": 3}


@pytest.mark.asyncio
async def test_run_discovery_source_failure_does_not_crash() -> None:
    """A failing source is logged and skipped; other sources still run."""
    conn = _make_conn()

    with patch("discovery.runner.discover_from_seed", new_callable=AsyncMock, side_effect=Exception("boom")), \
         patch("discovery.runner.discover_from_yc", new_callable=AsyncMock, return_value=5):

        results = await run_discovery(conn, _minimal_settings(), sources=["seed", "yc"])

    assert results["seed"] == 0   # failed → 0
    assert results["yc"] == 5     # still ran


@pytest.mark.asyncio
async def test_run_discovery_no_sources_returns_empty() -> None:
    """With no sources configured, run_discovery returns empty dict without error."""
    conn = _make_conn()
    settings = {"discovery": {"sources": {}}}
    results = await run_discovery(conn, settings, sources=None)
    assert results == {}


@pytest.mark.asyncio
async def test_run_discovery_disabled_returns_empty() -> None:
    """discovery.enabled: false skips all sources (even if configured)."""
    conn = _make_conn()
    settings = {"discovery": {"enabled": False, "sources": {"seed": True}}}
    with patch("discovery.runner.discover_from_seed", new_callable=AsyncMock) as mock_seed:
        results = await run_discovery(conn, settings, sources=None)
    mock_seed.assert_not_called()
    assert results == {}


def test_enabled_discovery_sources_github_trending_alias() -> None:
    """Legacy settings key github_trending enables the github source."""
    cfg = {"github_trending": True, "github": False, "seed": False}
    assert enabled_discovery_sources(cfg) == ["github"]


def test_enabled_discovery_sources_prefers_explicit_github() -> None:
    cfg = {"github": True, "seed": True}
    out = enabled_discovery_sources(cfg)
    assert out == ["seed", "github"]
