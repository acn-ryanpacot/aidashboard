"""Phase 4 back end: live settings, caching, feeds, calendars, system, briefing."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from jarvis_core.adapters.calendar.ics import IcsCalendarProvider, parse_ics
from jarvis_core.adapters.llm.ollama import OllamaLanguageModel, ThinkFilter
from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqlitePreferenceStore,
    SqliteReminderRepository,
    SqliteTaskRepository,
)
from jarvis_core.adapters.system.monitor import parse_nvidia_smi
from jarvis_core.adapters.web.rss import RssNewsProvider, merge_headlines, parse_feed
from jarvis_core.application.briefing import BriefingScheduler, BriefingService
from jarvis_core.application.cache import TtlCache
from jarvis_core.application.information import NewsService, ScheduleService, WeatherService
from jarvis_core.application.runtime_settings import (
    PREFERENCE_KEY,
    RuntimeSettings,
    SettingsError,
    SettingsService,
)
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.config import Settings
from jarvis_core.container import runtime_defaults
from jarvis_core.doctor import Status, check_ollama, check_python, run_checks
from jarvis_core.domain.models import ChatMessage, Role, TextDelta, ToolCall
from jarvis_core.domain.records import CalendarEvent, Headline
from tests.fakes import FakeCalendar, FakeNews, FakeWeather, FixedClock, MemoryPreferences

TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 10, 8, 0, tzinfo=TZ)


def defaults() -> RuntimeSettings:
    return runtime_defaults(Settings(_env_file=None))


# --------------------------------------------------------- runtime settings


async def test_settings_update_persists_only_overrides_and_notifies() -> None:
    store = MemoryPreferences()
    service = SettingsService(defaults(), store)
    seen: list[tuple[str, str]] = []
    service.on_change(lambda new, old: seen.append((old.tts_voice, new.tts_voice)))

    updated = await service.update({"tts_voice": "bm_lewis", "follow_up_ms": 0})
    assert updated.tts_voice == "bm_lewis"
    assert store.data[PREFERENCE_KEY] == {"tts_voice": "bm_lewis", "follow_up_ms": 0}
    assert seen == [("bm_george", "bm_lewis")]

    reloaded = SettingsService(defaults(), store)
    assert (await reloaded.load()).tts_voice == "bm_lewis"

    assert (await service.reset()).tts_voice == "bm_george"
    assert store.data[PREFERENCE_KEY] == {}


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"briefing_time": "7am"}, "briefing_time"),
        ({"wake_threshold": 2}, "wake_threshold"),
        ({"news_feeds": ["not a url"]}, "news_feeds"),
        ({"volume": 11}, "Unknown setting"),
    ],
)
async def test_invalid_settings_are_rejected_atomically(
    patch: dict[str, object], message: str
) -> None:
    service = SettingsService(defaults(), MemoryPreferences())
    with pytest.raises(SettingsError, match=message):
        await service.update({**patch, "tts_speed": 1.2})
    assert service.current.tts_speed == 1.0


async def test_corrupt_stored_settings_fall_back_to_defaults() -> None:
    store = MemoryPreferences()
    store.data[PREFERENCE_KEY] = {"wake_threshold": "loud"}
    service = SettingsService(defaults(), store)
    assert (await service.load()) == defaults()


async def test_applier_failure_does_not_break_update() -> None:
    service = SettingsService(defaults(), MemoryPreferences())

    def broken(new: RuntimeSettings, old: RuntimeSettings) -> None:
        raise RuntimeError("boom")

    service.on_change(broken)
    assert (await service.update({"user_name": "Tony"})).user_name == "Tony"


async def test_sqlite_preference_store_round_trip() -> None:
    store = SqlitePreferenceStore(Database(":memory:"))
    assert await store.get("layout") is None
    await store.set("layout", {"left": ["clock"]})
    await store.set("layout", {"left": ["weather"]})
    assert await store.get("layout") == {"left": ["weather"]}


# ------------------------------------------------------------------ cache


async def test_ttl_cache_shares_and_expires() -> None:
    now = [0.0]
    cache: TtlCache[int] = TtlCache(10, clock=lambda: now[0])
    calls = []

    async def load() -> int:
        calls.append(1)
        return len(calls)

    assert await cache.get("k", load) == 1
    assert await cache.get("k", load) == 1
    now[0] = 11
    assert await cache.get("k", load) == 2
    cache.clear()
    assert await cache.get("k", load) == 3


# ------------------------------------------------------------------ feeds

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>World News</title>
<item><title>Older story</title><link>https://n/1</link><pubDate>Mon, 09 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>  Newer   story </title><link>https://n/2</link><pubDate>Tue, 10 Nov 2026 07:00:00 +0000</pubDate></item>
<item><title></title><link>https://n/3</link></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Tech</title>
<entry><title>Atom story</title><link rel="alternate" href="https://a/1"/><updated>2026-11-10T06:00:00Z</updated></entry>
</feed>"""

RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel><title>Old School</title></channel>
<item><title>RDF story</title><link>https://r/1</link><dc:date>2026-11-08T12:00:00Z</dc:date></item>
</rdf:RDF>"""


def test_parse_rss_atom_and_rdf() -> None:
    rss = parse_feed(RSS)
    assert [h.title for h in rss] == ["Older story", "Newer story"]
    assert rss[0].source == "World News" and rss[0].published is not None
    atom = parse_feed(ATOM)
    assert (atom[0].title, atom[0].url, atom[0].source) == ("Atom story", "https://a/1", "Tech")
    assert parse_feed(RDF)[0].source == "Old School"
    with pytest.raises(ValueError, match="unsupported"):
        parse_feed(b"<html></html>")
    with pytest.raises(ValueError, match="XML"):
        parse_feed(b"<<not xml")


def test_merge_sorts_newest_first_and_dedupes() -> None:
    merged = merge_headlines([parse_feed(RSS), parse_feed(ATOM), parse_feed(RSS)], limit=10)
    assert [h.title for h in merged] == ["Newer story", "Atom story", "Older story"]


async def test_rss_provider_skips_broken_feeds() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(200, content=RSS) if "good" in str(request.url) else httpx.Response(500)
        )

    provider = RssNewsProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    headlines = await provider.headlines(["https://good.example/rss", "https://bad.example/rss"])
    assert len(headlines) == 2


async def test_news_service_caches_and_invalidates() -> None:
    fake = FakeNews()
    feeds = ["https://example.org/rss"]
    service = NewsService(fake, lambda: feeds)
    await service.headlines()
    await service.headlines()
    assert fake.calls == 1
    service.invalidate()
    await service.headlines()
    assert fake.calls == 2
    assert await NewsService(fake, lambda: []).headlines() == []


# --------------------------------------------------------------- calendar

ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
X-WR-CALNAME:Work
BEGIN:VEVENT
UID:1
SUMMARY:Standup
DTSTART:20261110T013000Z
DTEND:20261110T014500Z
RRULE:FREQ=DAILY;COUNT=5
LOCATION:Room 4
END:VEVENT
BEGIN:VEVENT
UID:2
SUMMARY:Holiday
DTSTART;VALUE=DATE:20261111
DTEND;VALUE=DATE:20261112
END:VEVENT
BEGIN:VEVENT
UID:3
SUMMARY:Out of range
DTSTART:20261201T010000Z
DTEND:20261201T020000Z
END:VEVENT
END:VCALENDAR
"""


def test_parse_ics_expands_recurrences_and_all_day_events() -> None:
    events = parse_ics(ICS, NOW.replace(hour=0), NOW.replace(hour=0) + timedelta(days=2), zone=TZ)
    assert [(e.title, e.start.hour, e.all_day) for e in events] == [
        ("Standup", 9, False),
        ("Holiday", 0, True),
        ("Standup", 9, False),
    ]
    assert events[0].location == "Room 4" and events[0].calendar == "Work"
    with pytest.raises(ValueError, match="iCalendar"):
        parse_ics("garbage", NOW, NOW)


async def test_ics_provider_reads_files_and_urls(tmp_path: Path) -> None:
    path = tmp_path / "family.ics"
    path.write_text(ICS, encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"  # webcal:// is fetched over https
        return httpx.Response(200, text=ICS)

    provider = IcsCalendarProvider(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    start = NOW.replace(hour=0)
    events = await provider.events(
        [str(path), "webcal://cal.example/secret.ics", str(path) + ".missing"],
        start,
        start + timedelta(days=1),
    )
    assert [e.title for e in events] == ["Standup", "Standup"]


async def test_schedule_service_day_and_upcoming() -> None:
    standup = CalendarEvent("Standup", NOW.replace(hour=9), NOW.replace(hour=9, minute=15))
    earlier = CalendarEvent("Gym", NOW.replace(hour=6), NOW.replace(hour=7))
    tomorrow = CalendarEvent("Dentist", NOW + timedelta(days=1), NOW + timedelta(days=1, hours=1))
    service = ScheduleService(
        FakeCalendar([earlier, standup, tomorrow]), lambda: ["x.ics"], clock=FixedClock(NOW)
    )
    assert [e.title for e in await service.day(0)] == ["Gym", "Standup"]
    assert [e.title for e in await service.day(1)] == ["Dentist"]
    assert [e.title for e in await service.upcoming(2)] == ["Standup", "Dentist"]
    assert not ScheduleService(FakeCalendar(), lambda: []).configured


# ---------------------------------------------------------------- system


def test_parse_nvidia_smi() -> None:
    output = "NVIDIA GeForce RTX 4070, 35, 4100, 12282, 51\nTesla T4, [N/A], 0, 15360, [N/A]\n"
    first, second = parse_nvidia_smi(output)
    assert (first.name, first.utilization_pct, first.temperature_c) == (
        "NVIDIA GeForce RTX 4070",
        35.0,
        51.0,
    )
    assert (second.utilization_pct, second.temperature_c) == (0.0, None)
    assert parse_nvidia_smi("") == ()


# --------------------------------------------------------------- ollama


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["<think>plan</think>Hello"], "Hello"),
        (["<thi", "nk>secret</th", "ink>Hi there"], "Hi there"),
        (["No thinking at all"], "No thinking at all"),
        (["a < b and <think>x</think> c"], "a < b and  c"),
        (["<think>never closed"], ""),
    ],
)
def test_think_filter(chunks: list[str], expected: str) -> None:
    hide = ThinkFilter()
    assert "".join(hide.feed(c) for c in chunks) + hide.flush() == expected


async def test_ollama_think_option_model_switch_and_listing() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "b:7b"}, {"name": "a:3b"}]})
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, text=json.dumps({"message": {"content": "<think>x</think>Yes"}, "done": True})
        )

    client = httpx.AsyncClient(base_url="http://o", transport=httpx.MockTransport(handler))
    llm = OllamaLanguageModel(base_url="http://o", model="a:3b", think=False, client=client)
    llm.set_model("b:7b")
    events = [e async for e in llm.stream_chat([ChatMessage(Role.USER, "hi")])]
    assert events == [TextDelta("Yes")]
    assert seen["think"] is False and seen["model"] == "b:7b" and llm.model == "b:7b"
    assert await llm.list_models() == ["a:3b", "b:7b"]


# --------------------------------------------------------------- briefing


async def _briefing() -> tuple[BriefingService, SqliteTaskRepository]:
    db = Database(":memory:")
    tasks = SqliteTaskRepository(db)
    reminders = SqliteReminderRepository(db)
    await tasks.add("Book flights")
    await reminders.add("Call mum", NOW.replace(hour=18))
    calendar = FakeCalendar(
        [CalendarEvent("Standup", NOW.replace(hour=9), NOW.replace(hour=9, minute=15))]
    )
    service = BriefingService(
        tasks=tasks,
        reminders=reminders,
        weather=WeatherService(FakeWeather(), lambda: "Manila"),
        schedule=ScheduleService(calendar, lambda: ["x.ics"], clock=FixedClock(NOW)),
        news=NewsService(FakeNews(), lambda: ["https://f"]),
        clock=FixedClock(NOW),
    )
    return service, tasks


async def test_briefing_facts_cover_every_section() -> None:
    service, _ = await _briefing()
    facts = await service.facts()
    assert "It is Tuesday 10 November, 8 AM." in facts
    assert "Weather in Manila: light rain, 21°C, high 24°C." in facts
    assert "Calendar today (1): 9 AM Standup." in facts
    assert "Open tasks (1): Book flights." in facts
    assert "Top headlines: Mars rover finds water ice" in facts


async def test_briefing_survives_failing_sections() -> None:
    class Broken:
        async def headlines(self, feeds: object, limit: int = 10) -> list[Headline]:
            raise RuntimeError("feed down")

    db = Database(":memory:")
    service = BriefingService(
        tasks=SqliteTaskRepository(db),
        reminders=SqliteReminderRepository(db),
        news=NewsService(Broken(), lambda: ["https://f"]),
        clock=FixedClock(NOW),
    )
    assert "Tasks: none open." in await service.facts()


async def test_briefing_scheduler_delivers_once_per_day() -> None:
    service, _ = await _briefing()
    announced: list[str] = []

    class Notifier:
        async def announce(self, kind: str, text: str) -> None:
            announced.append(text)

        async def data_changed(self, topic: str) -> None: ...

    clock = FixedClock(NOW.replace(hour=7, minute=29))
    store = MemoryPreferences()

    async def compose(prompt: str) -> str:
        return "Good morning, sir. " + prompt.splitlines()[-1]

    scheduler = BriefingScheduler(
        compose=compose,
        briefing=service,
        notifier=Notifier(),
        store=store,
        briefing_time=lambda: "07:30",
        has_listeners=lambda: True,
        clock=clock,
    )
    assert not await scheduler.tick()  # too early
    clock.now = NOW.replace(hour=7, minute=31)
    assert await scheduler.tick()
    assert not await scheduler.tick()  # already delivered today
    assert len(announced) == 1 and announced[0].startswith("Good morning, sir.")
    clock.now = NOW.replace(hour=11)  # outside the 3-hour window next day too
    store.data.clear()
    assert not await scheduler.tick()


async def test_briefing_and_data_tools() -> None:
    service, _ = await _briefing()
    standup = CalendarEvent(
        "Standup", NOW.replace(hour=9), NOW.replace(hour=9, minute=15), location="Room 4"
    )
    registry = ToolRegistry()
    registry.extend(builtin.briefing_tools(service))
    registry.extend(builtin.news_tools(NewsService(FakeNews(), lambda: ["https://f"])))
    registry.extend(
        builtin.schedule_tools(
            ScheduleService(FakeCalendar([standup]), lambda: ["x.ics"], clock=FixedClock(NOW)),
            clock=FixedClock(NOW),
        )
    )
    assert "Briefing facts" in await registry.execute(ToolCall("daily_briefing", {}))
    assert "Mars rover" in await registry.execute(ToolCall("get_headlines", {}))
    assert "No headlines found about cricket" in await registry.execute(
        ToolCall("get_headlines", {"topic": "cricket"})
    )
    assert "9 AM: Standup at Room 4" in await registry.execute(ToolCall("get_schedule", {}))
    assert "Nothing is scheduled tomorrow" in await registry.execute(
        ToolCall("get_schedule", {"day": "tomorrow"})
    )
    assert "Error" in await registry.execute(ToolCall("get_schedule", {"day": "someday"}))

    unconfigured = ToolRegistry()
    unconfigured.extend(builtin.schedule_tools(ScheduleService(FakeCalendar(), lambda: [])))
    assert "no calendar" in await unconfigured.execute(ToolCall("get_schedule", {}))


# ----------------------------------------------------------------- doctor


def test_doctor_runs_without_crashing() -> None:
    settings = Settings(_env_file=None, llm_base_url="http://127.0.0.1:9", port=9)
    results = run_checks(settings)
    names = {r.name for r in results}
    assert {"Python", "Ollama", "Data directory", "Port"} <= names
    assert check_python().status in (Status.OK, Status.WARN)
    [ollama] = check_ollama(settings)
    assert ollama.status is Status.FAIL and "ollama.com" in ollama.hint


def test_weather_service_uses_default_and_cache() -> None:
    service = WeatherService(FakeWeather(), lambda: "")
    assert service.default_location == ""


async def test_weather_service_returns_none_without_location() -> None:
    assert await WeatherService(FakeWeather(), lambda: "").current() is None
    report = await WeatherService(FakeWeather(), lambda: "Oslo").current()
    assert report is not None and report.location == "Oslo"


def test_now_constant_is_aware() -> None:
    assert NOW.tzinfo is not None and datetime.now(UTC).tzinfo is UTC
