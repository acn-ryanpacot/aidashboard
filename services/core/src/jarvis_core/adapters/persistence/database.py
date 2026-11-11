"""A tiny SQLite wrapper with forward-only, versioned migrations.

Why not an ORM? At personal scale (thousands of rows) the standard library is
fast, dependency-free and easy to inspect with any SQLite browser. See
``docs/adr/0008-sqlite-persistence.md``.
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

import structlog

log = structlog.get_logger(__name__)

T = TypeVar("T")

#: Ordered schema migrations. Never edit an applied migration — append a new one.
MIGRATIONS: tuple[str, ...] = (
    # 1 — tasks, reminders, long-term memory
    """
    CREATE TABLE tasks (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        title        TEXT    NOT NULL,
        done         INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT    NOT NULL,
        completed_at TEXT
    );
    CREATE TABLE reminders (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        text       TEXT    NOT NULL,
        due_at     TEXT    NOT NULL,
        delivered  INTEGER NOT NULL DEFAULT 0,
        created_at TEXT    NOT NULL
    );
    CREATE INDEX idx_reminders_pending ON reminders (delivered, due_at);
    CREATE TABLE memories (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        text       TEXT NOT NULL,
        embedding  BLOB,
        created_at TEXT NOT NULL
    );
    """,
    # 2 — local document index
    """
    CREATE TABLE document_chunks (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        path      TEXT    NOT NULL,
        mtime     REAL    NOT NULL,
        ordinal   INTEGER NOT NULL,
        text      TEXT    NOT NULL,
        embedding BLOB    NOT NULL
    );
    CREATE INDEX idx_document_chunks_path ON document_chunks (path);
    """,
    # 3 — UI layout, runtime settings and other small JSON documents
    """
    CREATE TABLE preferences (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """,
    # 4 — countdown timers
    """
    CREATE TABLE timers (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        label      TEXT    NOT NULL,
        duration_s INTEGER NOT NULL,
        ends_at    TEXT    NOT NULL,
        created_at TEXT    NOT NULL,
        done       INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX idx_timers_running ON timers (done, ends_at);
    """,
)


def to_db_time(value: datetime) -> str:
    """Serialise a timezone-aware datetime as a sortable UTC ISO-8601 string."""
    if value.tzinfo is None:
        raise ValueError("datetimes must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="seconds")


def from_db_time(value: str | None) -> datetime | None:
    """Parse a value written by :func:`to_db_time`."""
    return datetime.fromisoformat(value) if value else None


def utc_now() -> datetime:
    """The current time, timezone-aware, truncated to seconds."""
    return datetime.now(UTC).replace(microsecond=0)


class Database:
    """A single SQLite connection shared by the repositories.

    Queries run in a worker thread (:meth:`run`) behind a lock, so the event
    loop never blocks on disk I/O.

    Args:
        path: Database file, or ``":memory:"`` for tests.
    """

    def __init__(self, path: Path | str) -> None:
        if isinstance(path, Path):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    @property
    def schema_version(self) -> int:
        """The number of migrations applied."""
        version: int = self._conn.execute("PRAGMA user_version").fetchone()[0]
        return version

    async def run(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        """Run ``operation(connection)`` in a worker thread and return its result."""
        return await asyncio.to_thread(self._locked, operation)

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def _locked(self, operation: Callable[[sqlite3.Connection], T]) -> T:
        with self._lock:
            return operation(self._conn)

    def _migrate(self) -> None:
        current = self.schema_version
        for number, script in enumerate(MIGRATIONS[current:], start=current + 1):
            self._conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
            log.info("database_migrated", version=number)
