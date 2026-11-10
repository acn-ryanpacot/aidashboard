"""Reminder scheduler and the session hub."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteReminderRepository
from jarvis_core.application.hub import SessionHub
from jarvis_core.application.reminders import ReminderScheduler
from jarvis_core.domain.events import DataChanged
from tests.fakes import RecordingNotifier, RecordingSink

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


async def test_scheduler_delivers_due_reminders_once() -> None:
    repo = SqliteReminderRepository(Database(":memory:"))
    await repo.add("Take the bins out", NOW - timedelta(seconds=5))
    await repo.add("Later", NOW + timedelta(hours=2))
    notifier = RecordingNotifier()
    scheduler = ReminderScheduler(repo, notifier, user_name="Ryan", clock=lambda: NOW)

    assert await scheduler.tick() == 1
    assert notifier.announcements == [
        ("reminder", "Pardon the interruption, Ryan. A reminder: Take the bins out")
    ]
    assert notifier.topics == ["reminders"]
    assert await scheduler.tick() == 0
    assert len(await repo.upcoming()) == 1


class _AnnouncingSession:
    def __init__(self) -> None:
        self.heard: list[str] = []

    async def announce(self, kind: str, text: str) -> None:
        self.heard.append(text)


async def test_hub_broadcasts_to_every_session() -> None:
    hub = SessionHub()
    sessions = [_AnnouncingSession(), _AnnouncingSession()]
    sinks = [RecordingSink(), RecordingSink()]
    for session, sink in zip(sessions, sinks, strict=True):
        hub.register(session, sink)  # type: ignore[arg-type]
    assert len(hub) == 2

    await hub.announce("reminder", "Hello")
    await hub.data_changed("tasks")
    assert [s.heard for s in sessions] == [["Hello"], ["Hello"]]
    assert all(sink.of_type(DataChanged) == [DataChanged("tasks")] for sink in sinks)

    hub.unregister(sessions[0])  # type: ignore[arg-type]
    await hub.announce("reminder", "Again")
    assert sessions[0].heard == ["Hello"]
