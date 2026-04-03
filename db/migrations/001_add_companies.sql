-- Migration 001: Add companies and discovery_runs tables, add company_id to listings

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT,
    website TEXT,
    careers_url TEXT,
    feed_url TEXT,
    feed_platform TEXT,                   -- greenhouse | lever | ashby | workable
    feed_status TEXT DEFAULT 'pending',   -- pending | active | broken | no_feed
    feed_last_checked TEXT,
    feed_last_successful TEXT,
    consecutive_failures INTEGER DEFAULT 0,
    discovery_source TEXT,                -- seed | yc | hn_hiring | github | wellfound | manual
    description TEXT,
    industry TEXT,
    location TEXT,
    size_estimate TEXT,
    relevance_score INTEGER,
    relevance_reason TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_feed_url ON companies(feed_url);
CREATE INDEX IF NOT EXISTS idx_companies_feed_status ON companies(feed_status);
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(name);

CREATE TABLE IF NOT EXISTS discovery_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    companies_found INTEGER DEFAULT 0,
    companies_with_feeds INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running',        -- running | completed | failed
    error_message TEXT
);

-- Add company_id FK to listings (nullable; existing rows get NULL)
-- Wrapped in a no-op guard since SQLite will error on duplicate column
ALTER TABLE listings ADD COLUMN company_id INTEGER REFERENCES companies(id);
