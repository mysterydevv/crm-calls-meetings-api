PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS managers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    bin TEXT NOT NULL UNIQUE CHECK (length(bin) = 12),
    phone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'no_answer', 'refused', 'meeting_set')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    manager_id INTEGER NOT NULL REFERENCES managers(id),
    scheduled_at TEXT NOT NULL,
    original_scheduled_at TEXT NOT NULL,
    reschedule_count INTEGER NOT NULL DEFAULT 0 CHECK (reschedule_count >= 0),
    status TEXT NOT NULL DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'cancelled', 'completed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    manager_id INTEGER NOT NULL REFERENCES managers(id),
    result TEXT NOT NULL CHECK (result IN ('no_answer', 'refused', 'meeting_set')),
    meeting_id INTEGER NULL REFERENCES meetings(id),
    notes TEXT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_companies_status
    ON companies (status);

CREATE INDEX IF NOT EXISTS idx_meetings_manager_status
    ON meetings (manager_id, status, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_meetings_company_status
    ON meetings (company_id, status, scheduled_at);

CREATE INDEX IF NOT EXISTS idx_calls_company
    ON calls (company_id, created_at);
