"""Tests for pipeline/company_db.py using in-memory SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from pipeline.company_db import (
    finish_discovery_run,
    get_active_feed_companies,
    get_company_by_name,
    increment_feed_failures,
    insert_discovery_run,
    iter_companies,
    update_feed_status,
    update_feed_success,
    upsert_company,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_conn() -> sqlite3.Connection:
    """Create an in-memory SQLite connection with the full schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema = (_REPO_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    migration = (_REPO_ROOT / "db" / "migrations" / "001_add_companies.sql").read_text(
        encoding="utf-8"
    )
    # Apply migration; ignore duplicate column error for ALTER TABLE
    try:
        conn.executescript(migration)
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise
    conn.commit()
    return conn


def _sample_company(**overrides: object) -> dict:
    base: dict = {
        "name": "Acme Corp",
        "slug": "acme",
        "website": "https://acme.example.com",
        "feed_url": "https://boards.greenhouse.io/acme/feed",
        "feed_platform": "greenhouse",
        "feed_status": "active",
        "discovery_source": "seed",
    }
    base.update(overrides)
    return base


# --- upsert_company ---


def test_upsert_company_inserts_new() -> None:
    conn = _make_conn()
    cid = upsert_company(conn, _sample_company())
    assert cid > 0
    row = get_company_by_name(conn, "Acme Corp")
    assert row is not None
    assert row["feed_platform"] == "greenhouse"


def test_upsert_company_updates_existing_by_feed_url() -> None:
    conn = _make_conn()
    upsert_company(conn, _sample_company())
    # Update with same feed_url
    upsert_company(conn, _sample_company(description="Updated desc"))
    row = get_company_by_name(conn, "Acme Corp")
    assert row is not None
    assert row["description"] == "Updated desc"
    # Only one record should exist
    cur = conn.execute("SELECT COUNT(*) FROM companies")
    assert cur.fetchone()[0] == 1


def test_upsert_company_updates_by_name_when_no_feed_url() -> None:
    conn = _make_conn()
    data = _sample_company()
    del data["feed_url"]
    upsert_company(conn, data)
    upsert_company(conn, {**data, "website": "https://new.example.com"})
    cur = conn.execute("SELECT COUNT(*) FROM companies")
    assert cur.fetchone()[0] == 1


# --- get_active_feed_companies ---


def test_get_active_feed_companies_filters_inactive() -> None:
    conn = _make_conn()
    upsert_company(conn, _sample_company(feed_status="active"))
    upsert_company(
        conn,
        _sample_company(
            name="Broken Co",
            feed_url="https://boards.greenhouse.io/broken/feed",
            feed_status="broken",
        ),
    )
    active = get_active_feed_companies(conn)
    assert len(active) == 1
    assert active[0]["name"] == "Acme Corp"


# --- update_feed_success / update_feed_status / increment_feed_failures ---


def test_update_feed_success_resets_failures() -> None:
    conn = _make_conn()
    cid = upsert_company(conn, _sample_company(consecutive_failures=3, feed_status="broken"))
    update_feed_success(conn, cid)
    cur = conn.execute("SELECT * FROM companies WHERE id = ?", (cid,))
    row = cur.fetchone()
    assert row["consecutive_failures"] == 0
    assert row["feed_status"] == "active"
    assert row["feed_last_successful"] is not None


def test_increment_feed_failures_counts_up() -> None:
    conn = _make_conn()
    cid = upsert_company(conn, _sample_company())
    count1 = increment_feed_failures(conn, cid)
    count2 = increment_feed_failures(conn, cid)
    assert count1 == 1
    assert count2 == 2


def test_update_feed_status_sets_status() -> None:
    conn = _make_conn()
    cid = upsert_company(conn, _sample_company())
    update_feed_status(conn, cid, "no_feed")
    cur = conn.execute("SELECT feed_status FROM companies WHERE id = ?", (cid,))
    assert cur.fetchone()["feed_status"] == "no_feed"


# --- discovery_runs ---


def test_insert_and_finish_discovery_run() -> None:
    conn = _make_conn()
    run_id = insert_discovery_run(conn, "seed")
    assert run_id > 0
    cur = conn.execute("SELECT status FROM discovery_runs WHERE id = ?", (run_id,))
    assert cur.fetchone()["status"] == "running"

    finish_discovery_run(conn, run_id, companies_found=5, companies_with_feeds=3)
    cur = conn.execute("SELECT * FROM discovery_runs WHERE id = ?", (run_id,))
    row = cur.fetchone()
    assert row["status"] == "completed"
    assert row["companies_found"] == 5
    assert row["companies_with_feeds"] == 3


# --- iter_companies ---


def test_iter_companies_returns_all() -> None:
    conn = _make_conn()
    upsert_company(conn, _sample_company())
    upsert_company(
        conn,
        _sample_company(
            name="Beta Inc",
            feed_url="https://jobs.lever.co/beta/rss",
            feed_platform="lever",
        ),
    )
    companies = list(iter_companies(conn))
    assert len(companies) == 2
