"""SQLite implementations of the repository ports."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np

from jarvis_core.adapters.persistence.database import Database, from_db_time, to_db_time, utc_now
from jarvis_core.domain.records import MemoryRecord, Reminder, StoredMemory, Task


def _encode_vector(vector: Sequence[float] | None) -> bytes | None:
    return None if vector is None else np.asarray(vector, dtype=np.float32).tobytes()


def _decode_vector(blob: bytes | None) -> tuple[float, ...] | None:
    return None if blob is None else tuple(float(x) for x in np.frombuffer(blob, dtype=np.float32))


def _required_time(value: str) -> datetime:
    parsed = from_db_time(value)
    assert parsed is not None
    return parsed


# --------------------------------------------------------------------- tasks


def _task(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        done=bool(row["done"]),
        created_at=_required_time(row["created_at"]),
        completed_at=from_db_time(row["completed_at"]),
    )


class SqliteTaskRepository:
    """Implements :class:`~jarvis_core.domain.ports.TaskRepository`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, title: str) -> Task:
        """Create an open task."""

        def op(conn: sqlite3.Connection) -> Task:
            cursor = conn.execute(
                "INSERT INTO tasks (title, created_at) VALUES (?, ?) RETURNING *",
                (title.strip(), to_db_time(utc_now())),
            )
            return _task(cursor.fetchone())

        return await self._db.run(op)

    async def list_all(self, *, include_done: bool = False) -> list[Task]:
        """Open tasks first (newest first), then recently completed ones."""
        where = "" if include_done else "WHERE done = 0"
        sql = f"SELECT * FROM tasks {where} ORDER BY done ASC, created_at DESC, id DESC"
        return await self._db.run(lambda c: [_task(r) for r in c.execute(sql)])

    async def get(self, task_id: int) -> Task | None:
        """Fetch one task."""

        def op(conn: sqlite3.Connection) -> Task | None:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return _task(row) if row else None

        return await self._db.run(op)

    async def set_done(self, task_id: int, done: bool) -> Task | None:
        """Mark a task done or not done."""
        completed = to_db_time(utc_now()) if done else None

        def op(conn: sqlite3.Connection) -> Task | None:
            row = conn.execute(
                "UPDATE tasks SET done = ?, completed_at = ? WHERE id = ? RETURNING *",
                (int(done), completed, task_id),
            ).fetchone()
            return _task(row) if row else None

        return await self._db.run(op)

    async def delete(self, task_id: int) -> bool:
        """Delete a task."""
        return await self._db.run(
            lambda c: c.execute("DELETE FROM tasks WHERE id = ?", (task_id,)).rowcount > 0
        )


# ----------------------------------------------------------------- reminders


def _reminder(row: sqlite3.Row) -> Reminder:
    return Reminder(
        id=row["id"],
        text=row["text"],
        due_at=_required_time(row["due_at"]),
        delivered=bool(row["delivered"]),
        created_at=_required_time(row["created_at"]),
    )


class SqliteReminderRepository:
    """Implements :class:`~jarvis_core.domain.ports.ReminderRepository`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, text: str, due_at: datetime) -> Reminder:
        """Schedule a reminder."""

        def op(conn: sqlite3.Connection) -> Reminder:
            cursor = conn.execute(
                "INSERT INTO reminders (text, due_at, created_at) VALUES (?, ?, ?) RETURNING *",
                (text.strip(), to_db_time(due_at), to_db_time(utc_now())),
            )
            return _reminder(cursor.fetchone())

        return await self._db.run(op)

    async def upcoming(self) -> list[Reminder]:
        """Undelivered reminders, soonest first."""
        sql = "SELECT * FROM reminders WHERE delivered = 0 ORDER BY due_at ASC"
        return await self._db.run(lambda c: [_reminder(r) for r in c.execute(sql)])

    async def due(self, now: datetime) -> list[Reminder]:
        """Undelivered reminders whose time has come."""
        sql = "SELECT * FROM reminders WHERE delivered = 0 AND due_at <= ? ORDER BY due_at"
        return await self._db.run(
            lambda c: [_reminder(r) for r in c.execute(sql, (to_db_time(now),))]
        )

    async def mark_delivered(self, reminder_id: int) -> None:
        """Record that a reminder was announced."""
        await self._db.run(
            lambda c: c.execute("UPDATE reminders SET delivered = 1 WHERE id = ?", (reminder_id,))
        )

    async def delete(self, reminder_id: int) -> bool:
        """Cancel a reminder."""
        return await self._db.run(
            lambda c: c.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,)).rowcount > 0
        )


# ------------------------------------------------------------------ memories


def _memory(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"], text=row["text"], created_at=_required_time(row["created_at"])
    )


class SqliteMemoryStore:
    """Implements :class:`~jarvis_core.domain.ports.MemoryStore`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, text: str, embedding: Sequence[float] | None) -> MemoryRecord:
        """Store a memory."""

        def op(conn: sqlite3.Connection) -> MemoryRecord:
            cursor = conn.execute(
                "INSERT INTO memories (text, embedding, created_at) VALUES (?, ?, ?) RETURNING *",
                (text.strip(), _encode_vector(embedding), to_db_time(utc_now())),
            )
            return _memory(cursor.fetchone())

        return await self._db.run(op)

    async def all(self) -> list[StoredMemory]:
        """Every memory, newest first, with its embedding."""
        sql = "SELECT * FROM memories ORDER BY created_at DESC, id DESC"
        return await self._db.run(
            lambda c: [
                StoredMemory(_memory(r), _decode_vector(r["embedding"])) for r in c.execute(sql)
            ]
        )

    async def delete(self, memory_id: int) -> bool:
        """Forget a memory."""
        return await self._db.run(
            lambda c: c.execute("DELETE FROM memories WHERE id = ?", (memory_id,)).rowcount > 0
        )


# ---------------------------------------------------------- document chunks


class SqliteDocumentChunkStore:
    """Stores embedded passages of the user's local documents."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def indexed_files(self) -> dict[str, float]:
        """Map of indexed file path → modification time at indexing."""
        sql = "SELECT path, MAX(mtime) AS mtime FROM document_chunks GROUP BY path"
        return await self._db.run(lambda c: {r["path"]: r["mtime"] for r in c.execute(sql)})

    async def replace_file(
        self, path: str, mtime: float, chunks: Sequence[tuple[str, Sequence[float]]]
    ) -> None:
        """Atomically replace every chunk of ``path``."""

        def op(conn: sqlite3.Connection) -> None:
            conn.execute("BEGIN")
            try:
                conn.execute("DELETE FROM document_chunks WHERE path = ?", (path,))
                conn.executemany(
                    "INSERT INTO document_chunks (path, mtime, ordinal, text, embedding) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [
                        (path, mtime, i, text, _encode_vector(vector))
                        for i, (text, vector) in enumerate(chunks)
                    ],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        await self._db.run(op)

    async def remove_file(self, path: str) -> None:
        """Drop a file that no longer exists."""
        await self._db.run(
            lambda c: c.execute("DELETE FROM document_chunks WHERE path = ?", (path,))
        )

    async def all_chunks(self) -> list[tuple[str, str, tuple[float, ...]]]:
        """Every ``(path, text, embedding)``."""
        sql = "SELECT path, text, embedding FROM document_chunks"

        def op(conn: sqlite3.Connection) -> list[tuple[str, str, tuple[float, ...]]]:
            rows = conn.execute(sql).fetchall()
            return [(r["path"], r["text"], _decode_vector(r["embedding"]) or ()) for r in rows]

        return await self._db.run(op)


# --------------------------------------------------------------- preferences


class SqlitePreferenceStore:
    """Implements :class:`~jarvis_core.domain.ports.PreferenceStore`."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str) -> Any | None:
        """The stored JSON value for ``key``."""

        def op(conn: sqlite3.Connection) -> Any | None:
            row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
            return json.loads(row["value"]) if row else None

        return await self._db.run(op)

    async def set(self, key: str, value: Any) -> None:
        """Insert or replace ``key``."""
        payload = json.dumps(value, separators=(",", ":"))
        await self._db.run(
            lambda c: c.execute(
                "INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, payload, to_db_time(utc_now())),
            )
        )
