import sqlite3
import os
import logging

logger = logging.getLogger("replay.db")

DB_PATH = os.path.join(os.path.dirname(__file__), "replay_state.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_events (
    event_id        TEXT PRIMARY KEY,
    fragment_source TEXT NOT NULL,
    timestamp_raw   TEXT NOT NULL,
    timestamp_norm  TEXT NOT NULL,
    payload         TEXT NOT NULL,
    ingested_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replay_windows (
    window_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    window_start    TEXT NOT NULL,
    window_end      TEXT NOT NULL,
    event_ids       TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replay_cursor (
    cursor_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT NOT NULL,
    window_id       INTEGER NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0,
    last_event_ts   TEXT,
    checkpoint_ts   TEXT NOT NULL,
    state           TEXT NOT NULL DEFAULT 'active',
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retention_meta (
    window_id       INTEGER PRIMARY KEY,
    retain_until    TEXT NOT NULL,
    purged          INTEGER NOT NULL DEFAULT 0,
    purged_at       TEXT
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH, isolation_level="DEFERRED")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logger.info("removed stale replay state")
    conn = get_connection()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    logger.info("schema initialized: %s", DB_PATH)
