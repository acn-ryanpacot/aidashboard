"""SQLite repositories, migrations and the voiceprint file store."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jarvis_core.adapters.persistence.database import (
    MIGRATIONS,
    Database,
    from_db_time,
    to_db_time,
)
from jarvis_core.adapters.persistence.repositories import (
    SqliteDocumentChunkStore,
    SqliteMemoryStore,
    SqliteReminderRepository,
    SqliteTaskRepository,
)
from jarvis_core.adapters.persistence.voiceprint import FileVoiceprintStore


def test_migrations_apply_once(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "jarvis.db"
    db = Database(path)
    assert db.schema_version == len(MIGRATIONS)
    db.close()
    reopened = Database(path)  # no error re-running against an up-to-date schema
    assert reopened.schema_version == len(MIGRATIONS)
    reopened.close()


def test_time_round_trip_and_naive_rejection() -> None:
    moment = datetime(2026, 11, 10, 9, 30, 15, 999, tzinfo=UTC)
    assert from_db_time(to_db_time(moment)) == moment.replace(microsecond=0)
    assert from_db_time(None) is None
    with pytest.raises(ValueError, match="timezone"):
        to_db_time(datetime(2026, 1, 1))


async def test_tasks_crud() -> None:
    repo = SqliteTaskRepository(Database(":memory:"))
    first = await repo.add("  Buy milk ")
    second = await repo.add("Book flights")
    assert first.title == "Buy milk" and not first.done
    assert [t.id for t in await repo.list_all()] == [second.id, first.id]

    done = await repo.set_done(first.id, True)
    assert done is not None and done.done and done.completed_at is not None
    assert [t.id for t in await repo.list_all()] == [second.id]
    assert [t.id for t in await repo.list_all(include_done=True)] == [second.id, first.id]

    reopened = await repo.set_done(first.id, False)
    assert reopened is not None and reopened.completed_at is None
    assert await repo.get(999) is None
    assert await repo.set_done(999, True) is None
    assert await repo.delete(first.id) and not await repo.delete(first.id)


async def test_reminders_due_and_delivery() -> None:
    repo = SqliteReminderRepository(Database(":memory:"))
    now = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    past = await repo.add("Past", now - timedelta(minutes=1))
    future = await repo.add("Future", now + timedelta(hours=1))
    assert [r.id for r in await repo.upcoming()] == [past.id, future.id]
    assert [r.id for r in await repo.due(now)] == [past.id]
    await repo.mark_delivered(past.id)
    assert await repo.due(now) == []
    assert [r.id for r in await repo.upcoming()] == [future.id]
    assert await repo.delete(future.id)


async def test_memory_store_keeps_embeddings() -> None:
    store = SqliteMemoryStore(Database(":memory:"))
    await store.add("with vector", [0.5, -1.0, 2.0])
    await store.add("without vector", None)
    stored = await store.all()
    assert [m.record.text for m in stored] == ["without vector", "with vector"]
    assert stored[0].embedding is None
    assert stored[1].embedding == pytest.approx((0.5, -1.0, 2.0))
    assert await store.delete(stored[0].record.id)


async def test_document_chunk_store_replaces_atomically() -> None:
    store = SqliteDocumentChunkStore(Database(":memory:"))
    await store.replace_file("a.md", 1.0, [("one", [1.0, 0.0]), ("two", [0.0, 1.0])])
    await store.replace_file("a.md", 2.0, [("three", [1.0, 1.0])])
    await store.replace_file("b.md", 5.0, [("four", [0.0, 0.0])])
    assert await store.indexed_files() == {"a.md": 2.0, "b.md": 5.0}
    assert [text for _, text, _ in await store.all_chunks()] == ["three", "four"]
    await store.remove_file("b.md")
    assert await store.indexed_files() == {"a.md": 2.0}


def test_voiceprint_file_store(tmp_path: Path) -> None:
    store = FileVoiceprintStore(tmp_path / "vp" / "voiceprint.json")
    assert store.load() is None
    store.save([0.1, 0.2, 0.3])
    assert store.load() == pytest.approx([0.1, 0.2, 0.3])
    store.clear()
    store.clear()  # idempotent
    assert store.load() is None
