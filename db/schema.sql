CREATE TABLE IF NOT EXISTS listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hash TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    location_raw TEXT,
    location_city TEXT,
    location_country TEXT,
    remote_status TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT,
    description TEXT,
    raw_html TEXT,
    posted_date TEXT,

    fit_score INTEGER,
    fit_reason TEXT,
    pref_score INTEGER,
    pref_reason TEXT,
    comp_score INTEGER,
    comp_reason TEXT,
    overall_score REAL,

    status TEXT DEFAULT 'new',
    notes TEXT,
    scored_at TEXT,
    scraped_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_overall_score ON listings(overall_score DESC);
CREATE INDEX IF NOT EXISTS idx_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_source ON listings(source);
CREATE INDEX IF NOT EXISTS idx_created_at ON listings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_company ON listings(company);
