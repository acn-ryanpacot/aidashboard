"""Countdown timers: parsing, storage, ringing, tools and API."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import SqliteTimerRepository
from jarvis_core.api.app import create_app
from jarvis_core.application.timers import (
    TimerScheduler,
    parse_duration,
    parse_timer_request,
    spoken_duration,
    timer_name,
)
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.tools.routing import BUILTIN_GROUPS
from jarvis_core.config import Settings
from jarvis_core.container import assemble
from jarvis_core.domain.models import ToolCall
from tests.fakes import FakeLlm, FakeVad, FixedClock, RecordingNotifier

TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 11, 18, 0, tzinfo=TZ)


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("10 minutes", 600),
        ("10 min", 600),
        ("10m", 600),
        ("90 seconds", 90),
        ("45s", 45),
        ("1h30m", 5400),
        ("1 hour 30 minutes", 5400),
        ("1.5 hours", 5400),
        ("an hour and a half", 5400),
        ("half an hour", 1800),
        ("a quarter of an hour", 900),
        ("ten minutes", 600),
        ("forty-five minutes", 2700),
        ("2 minutes 30 seconds", 150),
        ("5", 300),  # a bare number is minutes
    ],
)
def test_parse_duration(text: str, seconds: int) -> None:
    assert parse_duration(text) == seconds


def test_labels_come_from_the_rest_of_the_request() -> None:
    assert parse_timer_request("12 min tea") == (720, "tea")
    assert parse_timer_request("set a timer for 10 minutes for the rice") == (600, "rice")
    assert parse_timer_request("pasta 8 minutes") == (480, "pasta")
    assert parse_timer_request("as soon as 5 min") == (300, "as soon as")  # "as" isn't seconds


@pytest.mark.parametrize("text", ["soon", "0 minutes", "25 hours", ""])
def test_invalid_durations(text: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)


def test_spoken_duration() -> None:
    assert spoken_duration(600) == "10 minutes"
    assert spoken_duration(5400) == "1 hour 30 minutes"
    assert spoken_duration(61) == "1 minute 1 second"
    assert spoken_duration(0) == "0 seconds"


# ------------------------------------------------------- storage & ringing


async def test_timers_ring_once() -> None:
    db = Database(":memory:")
    repo = SqliteTimerRepository(db)
    rice = await repo.add("rice", 600, NOW + timedelta(minutes=10))
    tea = await repo.add("", 120, NOW + timedelta(minutes=2))
    assert [t.id for t in await repo.active()] == [tea.id, rice.id]  # soonest first
    assert timer_name(rice) == "the rice timer" and timer_name(tea) == "the 2-minute timer"

    clock = FixedClock(NOW + timedelta(minutes=3))
    notifier = RecordingNotifier()
    scheduler = TimerScheduler(repo, notifier, user_name="Ryan", clock=clock)
    assert await scheduler.tick() == 1
    assert notifier.announcements == [("timer", "Ryan, the 2-minute timer is done.")]
    assert "timers" in notifier.topics
    assert await scheduler.tick() == 0  # rings once

    clock.now = NOW + timedelta(minutes=11)
    assert await scheduler.tick() == 1
    assert notifier.announcements[-1] == ("timer", "Ryan, the rice timer is done.")
    assert await repo.active() == []


# -------------------------------------------------------------------- tools


async def test_timer_tools() -> None:
    repo = SqliteTimerRepository(Database(":memory:"))
    clock = FixedClock(NOW)
    registry = ToolRegistry()
    registry.extend(builtin.timer_tools(repo, clock=clock))

    started = await registry.execute(
        ToolCall("set_timer", {"duration": "10 minutes", "label": "rice"})
    )
    assert started == "Started the rice timer for 10 minutes; it rings today at 6:10 PM."
    await registry.execute(ToolCall("set_timer", {"duration": 5}))  # a number means minutes

    clock.now = NOW + timedelta(minutes=2)
    listing = await registry.execute(ToolCall("list_timers", {}))
    assert "the 5-minute timer: 3 minutes left" in listing
    assert "the rice timer: 8 minutes left" in listing

    several = await registry.execute(ToolCall("cancel_timer", {}))
    assert several == "Error: several timers are running; ask which one"
    assert await registry.execute(ToolCall("cancel_timer", {"timer": "rice"})) == (
        "Cancelled the rice timer."
    )
    assert await registry.execute(ToolCall("cancel_timer", {})) == "Cancelled the 5-minute timer."
    assert (await registry.execute(ToolCall("set_timer", {"duration": "later"}))).startswith(
        "Error: no duration found"
    )


@pytest.mark.parametrize(
    "request_text",
    ["Set a timer for 10 minutes", "how much time is left", "cancel the countdown"],
)
def test_timer_requests_route_to_timer_tools(request_text: str) -> None:
    timers = next(g for g in BUILTIN_GROUPS if g.name == "timers")
    assert timers.matches(request_text)


# ---------------------------------------------------------------------- API


@pytest.fixture
def client() -> Iterator[TestClient]:
    container = assemble(
        Settings(_env_file=None),
        llm=FakeLlm(["ok"]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
    )
    with TestClient(create_app(container=container)) as test_client:
        yield test_client


def test_timers_rest(client: TestClient) -> None:
    created = client.post("/api/timers", json={"duration": "12 min tea"})
    assert created.status_code == 201
    body = created.json()
    assert body["label"] == "tea" and body["duration_s"] == 720
    explicit = client.post("/api/timers", json={"duration": "1h", "label": "Laundry"}).json()
    assert explicit["label"] == "Laundry"
    assert [t["label"] for t in client.get("/api/timers").json()] == ["tea", "Laundry"]

    assert client.delete(f"/api/timers/{body['id']}").status_code == 204
    assert client.delete(f"/api/timers/{body['id']}").status_code == 404
    bad = client.post("/api/timers", json={"duration": "eventually"})
    assert bad.status_code == 422 and "no duration" in bad.json()["detail"]
