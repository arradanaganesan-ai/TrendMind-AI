"""SQLite persistence layer.

Uses parameterized queries exclusively. The schema is created idempotently on
startup (documented initialization strategy — no external migration tool).
No secrets are ever stored here.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS research (
    id            TEXT PRIMARY KEY,
    query         TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    search_mode   TEXT NOT NULL DEFAULT 'demo',
    ai_mode       TEXT NOT NULL DEFAULT 'basic',
    status        TEXT NOT NULL DEFAULT 'pending',
    result_count  INTEGER NOT NULL DEFAULT 0,
    filters_json  TEXT,
    results_json  TEXT,
    report_json   TEXT,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_research_created ON research(created_at DESC);

CREATE TABLE IF NOT EXISTS saved_topic (
    id         TEXT PRIMARY KEY,
    topic      TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_topic_created ON saved_topic(created_at DESC);
"""


class Database:
    """Thread-safe SQLite wrapper with a connection per thread."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._local = threading.local()
        self._write_lock = threading.Lock()
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._path, timeout=10.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def initialize(self) -> None:
        with self._write_lock:
            conn = self._conn()
            conn.executescript(SCHEMA)
            conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialized write transaction."""
        with self._write_lock:
            conn = self._conn()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        conn = self._conn()
        return list(conn.execute(sql, params).fetchall())

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self.transaction() as conn:
            conn.execute(sql, params)

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


_db: Database | None = None
_db_lock = threading.Lock()


def get_db(path: str) -> Database:
    """Return the process-wide database instance, creating it on first use."""
    global _db
    with _db_lock:
        if _db is None or _db._path != path:  # noqa: SLF001 - internal accessor
            _db = Database(path)
        return _db


def reset_db_for_tests() -> None:
    """Drop the cached database instance (tests only)."""
    global _db
    with _db_lock:
        _db = None
