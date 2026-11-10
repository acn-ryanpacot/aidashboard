"""Built-in tools against the real SQLite repositories and fake providers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqliteMemoryStore,
    SqliteReminderRepository,
    SqliteTaskRepository,
)
from jarvis_core.application.memory import MemoryService
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import Tool, ToolError, ToolRegistry
from jarvis_core.application.tools.timeparse import resolve_due_time, spoken_time
from jarvis_core.domain.models import ToolCall
from tests.fakes import (
    FakeDocuments,
    FakeEmbedder,
    FakeKnowledge,
    FakeSearch,
    FakeWeather,
    FixedClock,
    RecordingNotifier,
)

TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 10, 14, 30, tzinfo=TZ)  # a Tuesday


def registry_with(*groups: list[Tool]) -> ToolRegistry:
    registry = ToolRegistry()
    for group in groups:
        registry.extend(group)
    return registry


async def call(registry: ToolRegistry, name: str, **arguments: object) -> str:
    return await registry.execute(ToolCall(name, arguments))


# ----------------------------------------------------------------- time


async def test_current_time() -> None:
    registry = registry_with(builtin.time_tools(FixedClock(NOW)))
    assert "Tuesday 10 November 2026, 14:30" in await call(registry, "get_current_time")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"in_minutes": 15, "at": None}, NOW + timedelta(minutes=15)),
        ({"in_minutes": None, "at": "16:00"}, NOW.replace(hour=16, minute=0)),
        ({"in_minutes": None, "at": "09:00"}, (NOW + timedelta(days=1)).replace(hour=9, minute=0)),
        ({"in_minutes": None, "at": "2026-11-12T08:15"}, datetime(2026, 11, 12, 8, 15, tzinfo=TZ)),
        ({"in_minutes": None, "at": "2026-11-12 08:15"}, datetime(2026, 11, 12, 8, 15, tzinfo=TZ)),
    ],
)
def test_resolve_due_time(kwargs: dict[str, object], expected: datetime) -> None:
    assert resolve_due_time(NOW, **kwargs) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"in_minutes": None, "at": None},
        {"in_minutes": -5, "at": None},
        {"in_minutes": None, "at": "2020-01-01T10:00"},
        {"in_minutes": None, "at": "half past nine"},
    ],
)
def test_resolve_due_time_errors(kwargs: dict[str, object]) -> None:
    with pytest.raises(ToolError):
        resolve_due_time(NOW, **kwargs)  # type: ignore[arg-type]


def test_spoken_time() -> None:
    assert spoken_time(NOW.replace(hour=15, minute=5), NOW) == "today at 3:05 PM"
    assert spoken_time(NOW + timedelta(days=1, hours=-5, minutes=-30), NOW) == "tomorrow at 9 AM"
    assert spoken_time(NOW + timedelta(days=3), NOW) == "on Friday 13 November at 2:30 PM"


# ---------------------------------------------------------------- tasks


async def test_task_lifecycle_and_notifications() -> None:
    repo = SqliteTaskRepository(Database(":memory:"))
    notifier = RecordingNotifier()
    registry = registry_with(builtin.task_tools(repo, notifier))

    assert await call(registry, "list_tasks") == "The task list is empty."
    assert await call(registry, "add_task", title="Buy milk") == "Added task #1: Buy milk."
    await call(registry, "add_task", title="Book flights")
    assert "2 open task(s)" in await call(registry, "list_tasks")
    assert await call(registry, "complete_task", task="milk") == "Marked 'Buy milk' as done."
    assert await call(registry, "complete_task", task="2") == "Marked 'Book flights' as done."
    assert notifier.topics == ["tasks"] * 4


async def test_task_matching_errors() -> None:
    repo = SqliteTaskRepository(Database(":memory:"))
    registry = registry_with(builtin.task_tools(repo))
    await call(registry, "add_task", title="Call mum")
    await call(registry, "add_task", title="Call the bank")
    assert "several tasks" in await call(registry, "complete_task", task="call")
    assert "no open task" in await call(registry, "complete_task", task="dentist")
    assert "required" in await call(registry, "add_task", title="  ")


# ------------------------------------------------------------ reminders


async def test_reminder_lifecycle() -> None:
    repo = SqliteReminderRepository(Database(":memory:"))
    notifier = RecordingNotifier()
    registry = registry_with(builtin.reminder_tools(repo, notifier, FixedClock(NOW)))

    result = await call(registry, "set_reminder", text="Stretch", in_minutes=30)
    assert result == "Reminder #1 set for today at 3 PM: Stretch."
    assert "tomorrow at 8 AM" in await call(registry, "set_reminder", text="Gym", at="08:00")
    assert "2 upcoming" in await call(registry, "list_reminders")
    assert (
        await call(registry, "cancel_reminder", reminder="gym") == "Cancelled the reminder 'Gym'."
    )
    assert "has already passed" in await call(
        registry, "set_reminder", text="Late", at="2020-01-01T00:00"
    )
    assert notifier.topics == ["reminders"] * 3


# --------------------------------------------------------------- memory


async def test_memory_tools() -> None:
    memory = MemoryService(SqliteMemoryStore(Database(":memory:")), FakeEmbedder(), min_score=0.2)
    registry = registry_with(builtin.memory_tools(memory))
    await call(registry, "remember", fact="Ryan's car is a blue hatchback")
    assert "blue hatchback" in await call(registry, "recall", query="what car do I drive")
    assert "Forgot" in await call(registry, "forget", query="car hatchback")
    assert await call(registry, "recall", query="car") == "Nothing relevant is stored in memory."
    assert "Error" in await call(registry, "forget", query="car")


# ---------------------------------------------------------- information


async def test_weather_tool() -> None:
    registry = registry_with(builtin.weather_tools(FakeWeather(), default_location="Manila"))
    result = await call(registry, "get_weather")
    assert result.startswith("Manila: light rain, 21°C")
    assert "high 24°C, low 18°C" in result
    assert "could not find" in await call(registry, "get_weather", location="Atlantis")

    no_default = registry_with(builtin.weather_tools(FakeWeather()))
    assert "no location" in await call(no_default, "get_weather")


async def test_knowledge_search_and_documents_tools() -> None:
    registry = registry_with(
        builtin.knowledge_tools(FakeKnowledge()),
        builtin.web_search_tools(FakeSearch()),
        builtin.document_tools(FakeDocuments()),
    )
    assert (await call(registry, "lookup_encyclopedia", topic="tokyo")).startswith("Tokyo:")
    assert "no article" in await call(registry, "lookup_encyclopedia", topic="nothing")
    assert "Result for news" in await call(registry, "web_search", query="news")
    assert "[notes.md]" in await call(registry, "search_documents", query="passport")
    assert "Nothing relevant" in await call(registry, "search_documents", query="nothing")
