"""Notifications center: history of announcements, REST, 'what did I miss?'."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jarvis_core.adapters.persistence.database import Database, to_db_time
from jarvis_core.adapters.persistence.repositories import (
    NOTIFICATION_MAX_ROWS,
    SqliteNotificationRepository,
)
from jarvis_core.api.app import create_app
from jarvis_core.application.hub import SessionHub
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.tools.routing import BUILTIN_GROUPS
from jarvis_core.config import Settings
from jarvis_core.container import Container, assemble
from jarvis_core.domain.models import ToolCall
from tests.fakes import LOCAL, FakeLlm, FakeVad, RecordingNotifier


async def test_history_and_read_state() -> None:
    repo = SqliteNotificationRepository(Database(":memory:"))
    first = await repo.add("timer", "Ryan, the rice timer is done.")
    second = await repo.add("alert", "Pardon me, Ryan. PisoTiyempo alert: …")
    assert [n.id for n in await repo.recent()] == [second.id, first.id]  # newest first
    assert [n.id for n in await repo.unread()] == [first.id, second.id]  # oldest first

    assert await repo.mark_read([first.id]) == 1
    assert [n.id for n in await repo.unread()] == [second.id]
    assert await repo.mark_read([]) == 0
    assert await repo.mark_read() == 1
    assert await repo.unread() == []
    assert (await repo.recent(1))[0].read

    await repo.clear()
    assert await repo.recent() == []


async def test_old_and_excess_entries_are_pruned() -> None:
    db = Database(":memory:")
    repo = SqliteNotificationRepository(db)
    old = to_db_time(datetime.now(UTC) - timedelta(days=40))

    def seed(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO notifications (kind, text, created_at) VALUES ('reminder', 'old', ?)",
            (old,),
        )

    await db.run(seed)
    for i in range(NOTIFICATION_MAX_ROWS + 5):
        await repo.add("timer", f"#{i}")
    items = await repo.recent(1000)
    assert len(items) == NOTIFICATION_MAX_ROWS
    assert all(n.text != "old" for n in items)
    assert items[0].text == f"#{NOTIFICATION_MAX_ROWS + 4}"


async def test_every_announcement_is_recorded_even_with_no_window_open() -> None:
    repo = SqliteNotificationRepository(Database(":memory:"))
    hub = SessionHub(repo)
    await hub.announce("reminder", "Pardon the interruption, Ryan. A reminder: dentist")
    [item] = await repo.recent()
    assert (item.kind, item.read) == ("reminder", False)


async def test_what_did_i_miss() -> None:
    repo = SqliteNotificationRepository(Database(":memory:"))
    notifier = RecordingNotifier()
    registry = ToolRegistry()
    registry.extend(builtin.notification_tools(repo, notifier))

    assert "Nothing new" in await registry.execute(ToolCall("get_notifications", {}))
    await repo.add("timer", "Ryan, the tea timer is done.")
    await repo.add("alert", "JFC closed at 252.40 pesos, above your 250.00 pesos alert.")
    text = await registry.execute(ToolCall("get_notifications", {}))
    assert text.startswith("2 unread announcement(s), oldest first:")
    assert "(timer): Ryan, the tea timer is done." in text and "(alert): JFC" in text
    assert await repo.unread() == []  # hearing them counts as seeing them
    assert notifier.topics == ["notifications"]


@pytest.mark.parametrize(
    "request_text", ["What did I miss?", "any notifications", "anything new while I was out"]
)
def test_missed_requests_route_to_notifications(request_text: str) -> None:
    group = next(g for g in BUILTIN_GROUPS if g.name == "notifications")
    assert group.matches(request_text)


# --------------------------------------------------------------------- API


@pytest.fixture
def container() -> Container:
    return assemble(
        Settings(_env_file=None),
        llm=FakeLlm(["ok"]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
    )


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container=container), client=LOCAL) as test_client:
        yield test_client


async def test_notifications_rest(container: Container, client: TestClient) -> None:
    await container.hub.announce("timer", "Ryan, the eggs timer is done.")
    await container.hub.announce("briefing", "Good morning, Ryan.")
    body = client.get("/api/notifications").json()
    assert body["unread"] == 2
    assert [n["kind"] for n in body["items"]] == ["briefing", "timer"]

    first_id = body["items"][1]["id"]
    partly = client.post("/api/notifications/read", json={"ids": [first_id]}).json()
    assert partly["unread"] == 1
    assert client.post("/api/notifications/read", json={}).json()["unread"] == 0
    assert client.get("/api/notifications?limit=1").json()["items"][0]["kind"] == "briefing"

    assert client.delete("/api/notifications").status_code == 204
    assert client.get("/api/notifications").json() == {"unread": 0, "items": []}
