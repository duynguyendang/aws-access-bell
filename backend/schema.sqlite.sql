PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT 'ring',
    device_id TEXT,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ingested',
    triage_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    event_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_device_kind ON events(device_id, kind);
CREATE INDEX IF NOT EXISTS idx_events_occurred_at ON events(occurred_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_hash ON events(event_hash);

CREATE TABLE IF NOT EXISTS expected_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'alexa',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS labels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    pattern_key TEXT NOT NULL,
    label TEXT NOT NULL,
    confirmed_at TEXT NOT NULL DEFAULT (datetime('now')),
    source TEXT NOT NULL DEFAULT 'alexa',
    FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_labels_pattern ON labels(pattern_key);

CREATE TABLE IF NOT EXISTS share_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brief_date TEXT NOT NULL,
    recipient TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS access_prefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL DEFAULT 'both',
    language TEXT NOT NULL DEFAULT 'en',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO access_prefs (id, mode, language) VALUES (1, 'both', 'en');

CREATE TABLE IF NOT EXISTS escalation_contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    recipient TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'sms',
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS escalation_policy (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0,
    timeout_seconds INTEGER NOT NULL DEFAULT 90,
    min_urgency INTEGER NOT NULL DEFAULT 7
);

INSERT OR IGNORE INTO escalation_policy (id) VALUES (1);

CREATE TABLE IF NOT EXISTS escalation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    contact_id INTEGER,
    recipient TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS escalation_pending (
    event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    fire_at TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Self-heal pre-CASCADE schemas: recreate escalation_pending with the FK in place.
-- The legacy table is renamed out of the way (no row copy), matching rows are
-- inserted into the fresh table, then the legacy table is dropped.
CREATE TABLE IF NOT EXISTS escalation_pending_fix (
    event_id INTEGER PRIMARY KEY REFERENCES events(id) ON DELETE CASCADE,
    fire_at TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
ALTER TABLE escalation_pending RENAME TO escalation_pending_legacy;
INSERT OR IGNORE INTO escalation_pending_fix (event_id, fire_at, timeout_seconds, created_at)
    SELECT ep.event_id, ep.fire_at, ep.timeout_seconds, ep.created_at
    FROM escalation_pending_legacy ep JOIN events e ON e.id = ep.event_id;
DROP TABLE escalation_pending_legacy;
ALTER TABLE escalation_pending_fix RENAME TO escalation_pending;