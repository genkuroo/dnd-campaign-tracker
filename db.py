"""SQLite bootstrap for the campaign tracker.

Phase 0 establishes the connection pattern and a schema-version table. The real
schema (the creature engine + the visibility-aware entity model) arrives in
Phase 1 — see CLAUDE.md.
"""
import sqlite3

DB_PATH = "campaign.db"

# Bumped as migrations are added in later phases.
SCHEMA_VERSION = 0


def get_connection():
    """Return a SQLite connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the database file and bootstrap tables if they don't exist."""
    conn = get_connection()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)"
            "  ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        conn.commit()
    finally:
        conn.close()
