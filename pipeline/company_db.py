"""SQLite access for the companies and discovery_runs tables."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterator


def get_active_feed_companies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all companies with feed_status='active' and a non-null feed_url."""
    cur = conn.execute(
        "SELECT * FROM companies WHERE feed_status = 'active' AND feed_url IS NOT NULL"
    )
    return cur.fetchall()


def get_company_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    """Look up a company by name (case-insensitive)."""
    cur = conn.execute(
        "SELECT * FROM companies WHERE lower(name) = lower(?)",
        (name,),
    )
    return cur.fetchone()


def get_company_by_feed_url(conn: sqlite3.Connection, feed_url: str) -> sqlite3.Row | None:
    """Look up a company by its feed URL."""
    cur = conn.execute("SELECT * FROM companies WHERE feed_url = ?", (feed_url,))
    return cur.fetchone()


def upsert_company(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    """Insert or update a company record. Matches on feed_url if present, else name.

    Returns the company id.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Try to find existing record
    existing: sqlite3.Row | None = None
    if data.get("feed_url"):
        existing = get_company_by_feed_url(conn, data["feed_url"])
    if existing is None and data.get("name"):
        existing = get_company_by_name(conn, data["name"])

    if existing is None:
        data.setdefault("created_at", now)
        data["updated_at"] = now
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" * len(data))
        conn.execute(
            f"INSERT INTO companies ({cols}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        cur = conn.execute("SELECT last_insert_rowid()")
        return int(cur.fetchone()[0])
    else:
        company_id = int(existing["id"])
        data["updated_at"] = now
        set_clause = ", ".join(f"{k} = ?" for k in data if k not in ("id", "created_at"))
        vals = [v for k, v in data.items() if k not in ("id", "created_at")]
        vals.append(company_id)
        conn.execute(
            f"UPDATE companies SET {set_clause} WHERE id = ?",
            vals,
        )
        return company_id


def update_feed_status(
    conn: sqlite3.Connection,
    company_id: int,
    status: str,
    error: str | None = None,
) -> None:
    """Update feed_status and feed_last_checked for a company."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE companies
        SET feed_status = ?, feed_last_checked = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, now, now, company_id),
    )


def update_feed_success(conn: sqlite3.Connection, company_id: int) -> None:
    """Mark a feed as successfully fetched: reset failures, update timestamps."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE companies
        SET feed_status = 'active',
            feed_last_checked = ?,
            feed_last_successful = ?,
            consecutive_failures = 0,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, now, company_id),
    )


def increment_feed_failures(conn: sqlite3.Connection, company_id: int) -> int:
    """Increment consecutive_failures counter. Returns the new count."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE companies
        SET consecutive_failures = consecutive_failures + 1,
            feed_last_checked = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (now, now, company_id),
    )
    cur = conn.execute(
        "SELECT consecutive_failures FROM companies WHERE id = ?",
        (company_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row else 0


def insert_discovery_run(conn: sqlite3.Connection, source: str) -> int:
    """Start a discovery run record. Returns the run id."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO discovery_runs (source, started_at, status) VALUES (?, ?, 'running')",
        (source, now),
    )
    cur = conn.execute("SELECT last_insert_rowid()")
    return int(cur.fetchone()[0])


def finish_discovery_run(
    conn: sqlite3.Connection,
    run_id: int,
    companies_found: int,
    companies_with_feeds: int,
    status: str = "completed",
    error: str | None = None,
) -> None:
    """Finish a discovery run record."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE discovery_runs
        SET finished_at = ?,
            companies_found = ?,
            companies_with_feeds = ?,
            status = ?,
            error_message = ?
        WHERE id = ?
        """,
        (now, companies_found, companies_with_feeds, status, error, run_id),
    )


def iter_companies(
    conn: sqlite3.Connection,
    limit: int | None = None,
) -> Iterator[sqlite3.Row]:
    """Iterate all companies ordered by relevance_score DESC."""
    q = "SELECT * FROM companies ORDER BY relevance_score DESC NULLS LAST, name ASC"
    args: tuple[Any, ...] = ()
    if limit is not None:
        q += " LIMIT ?"
        args = (limit,)
    cur = conn.execute(q, args)
    yield from cur.fetchall()


def get_companies_for_dashboard(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all companies with listing counts for the dashboard."""
    cur = conn.execute(
        """
        SELECT
            c.*,
            COUNT(l.id) AS listing_count
        FROM companies c
        LEFT JOIN listings l ON l.company_id = c.id
        GROUP BY c.id
        ORDER BY c.feed_status ASC, c.relevance_score DESC NULLS LAST, c.name ASC
        """
    )
    return cur.fetchall()
