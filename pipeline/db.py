"""SQLite access for listings."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterator

from pipeline.config_paths import REPO_ROOT


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Apply schema.sql and any pending migrations in db/migrations/."""
    schema_file = REPO_ROOT / "db" / "schema.sql"
    conn.executescript(schema_file.read_text(encoding="utf-8"))

    migrations_dir = REPO_ROOT / "db" / "migrations"
    if migrations_dir.is_dir():
        for mig in sorted(migrations_dir.glob("*.sql")):
            try:
                conn.executescript(mig.read_text(encoding="utf-8"))
            except sqlite3.OperationalError as e:
                # ALTER TABLE ADD COLUMN errors on already-migrated DBs
                if "duplicate column" not in str(e).lower():
                    raise

    conn.commit()


@contextmanager
def connect(db_file: Path) -> Generator[sqlite3.Connection, None, None]:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        ensure_schema(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_by_hash(conn: sqlite3.Connection, h: str) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM listings WHERE hash = ?", (h,))
    row = cur.fetchone()
    return row


def scored_within_days(row: sqlite3.Row | None, days: int = 7) -> bool:
    """True if row exists and scored_at is within last `days` days."""
    if row is None:
        return False
    scored_at = row["scored_at"]
    if not scored_at:
        return False
    try:
        # SQLite may store "2025-03-01 12:00:00" or ISO
        dt = datetime.fromisoformat(str(scored_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() < days * 86400


def insert_listing(conn: sqlite3.Connection, row: dict[str, Any]) -> None:
    """Insert a new listing row (all keys must match columns)."""
    cols = ", ".join(row.keys())
    placeholders = ", ".join("?" * len(row))
    conn.execute(f"INSERT INTO listings ({cols}) VALUES ({placeholders})", tuple(row.values()))


def update_scores(
    conn: sqlite3.Connection,
    h: str,
    scores: dict[str, Any],
) -> None:
    """Update LLM scores and metadata for hash."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE listings SET
            fit_score = ?, fit_reason = ?,
            pref_score = ?, pref_reason = ?,
            comp_score = ?, comp_reason = ?,
            overall_score = ?,
            scored_at = ?,
            updated_at = ?
        WHERE hash = ?
        """,
        (
            scores["fit_score"],
            scores["fit_reason"],
            scores["pref_score"],
            scores["pref_reason"],
            scores["comp_score"],
            scores["comp_reason"],
            scores["overall_score"],
            now,
            now,
            h,
        ),
    )


def upsert_listing_after_scrape(
    conn: sqlite3.Connection,
    data: dict[str, Any],
) -> None:
    """Insert new listing or update non-score fields if hash exists (keep existing scores unless caller rescored)."""
    h = data["hash"]
    existing = get_by_hash(conn, h)
    if existing is None:
        try:
            insert_listing(conn, data)
            return
        except sqlite3.IntegrityError:
            pass
    # Update mutable fields but preserve scores/status/notes unless this is a full replace
    conn.execute(
        """
        UPDATE listings SET
            source = ?, source_url = ?, title = ?, company = ?,
            location_raw = ?, location_city = ?, location_country = ?,
            remote_status = ?, salary_min = ?, salary_max = ?, salary_currency = ?,
            description = ?, raw_html = ?, posted_date = ?,
            scraped_at = ?, updated_at = ?, company_id = ?
        WHERE hash = ?
        """,
        (
            data["source"],
            data.get("source_url"),
            data["title"],
            data["company"],
            data.get("location_raw"),
            data.get("location_city"),
            data.get("location_country"),
            data.get("remote_status"),
            data.get("salary_min"),
            data.get("salary_max"),
            data.get("salary_currency"),
            data.get("description"),
            data.get("raw_html"),
            data.get("posted_date"),
            data["scraped_at"],
            datetime.now(timezone.utc).isoformat(),
            data.get("company_id"),
            h,
        ),
    )


def update_listing_status(conn: sqlite3.Connection, listing_id: int, status: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE listings SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, listing_id),
    )


def update_listing_notes(conn: sqlite3.Connection, listing_id: int, notes: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE listings SET notes = ?, updated_at = ? WHERE id = ?",
        (notes, now, listing_id),
    )


def get_listing_by_id(conn: sqlite3.Connection, listing_id: int) -> sqlite3.Row | None:
    cur = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,))
    return cur.fetchone()


def iter_listings(conn: sqlite3.Connection, limit: int | None = None) -> Iterator[sqlite3.Row]:
    q = "SELECT * FROM listings ORDER BY created_at DESC"
    args: tuple[Any, ...] = ()
    if limit is not None:
        q += " LIMIT ?"
        args = (limit,)
    cur = conn.execute(q, args)
    yield from cur.fetchall()
