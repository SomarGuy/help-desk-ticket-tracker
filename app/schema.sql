-- Database schema for the help desk ticket tracker (SQLite).
-- Timestamps are stored as ISO-8601 UTC text, e.g. 2026-03-02T14:05:00.

DROP TABLE IF EXISTS notes;
DROP TABLE IF EXISTS tickets;
DROP TABLE IF EXISTS technicians;

CREATE TABLE technicians (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE tickets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    requester      TEXT NOT NULL,
    category       TEXT NOT NULL CHECK (category IN ('Hardware','Software','Network','Account Access')),
    priority       TEXT NOT NULL CHECK (priority IN ('Low','Medium','High','Critical')),
    status         TEXT NOT NULL DEFAULT 'Open'
                   CHECK (status IN ('Open','In Progress','Waiting on User','Resolved','Closed')),
    assignee_id    INTEGER REFERENCES technicians(id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    due_at         TEXT NOT NULL,          -- SLA due time, derived from priority
    resolved_at    TEXT,                   -- set when status becomes Resolved/Closed
    resolution     TEXT                    -- required to resolve/close
);

-- The resolution log: free-text notes plus automatic entries for changes.
CREATE TABLE notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id  INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    author     TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('note','change','resolution')),
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_tickets_status   ON tickets(status);
CREATE INDEX idx_tickets_category ON tickets(category);
CREATE INDEX idx_notes_ticket     ON notes(ticket_id);
