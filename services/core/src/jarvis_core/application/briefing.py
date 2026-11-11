"""The morning briefing: weather, schedule, tasks, reminders and headlines in one go."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime

import structlog

from jarvis_core.application.information import NewsService, ScheduleService, WeatherService
from jarvis_core.application.portfolio import PortfolioService, describe_portfolio
from jarvis_core.domain.ports import Notifier, PreferenceStore, ReminderRepository, TaskRepository

log = structlog.get_logger(__name__)

Clock = Callable[[], datetime]
LAST_BRIEFING_KEY = "briefing_last_date"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _clock_label(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")


class BriefingService:
    """Gathers the facts for a briefing. Every section is optional and fail-safe.

    Args:
        tasks: Open tasks.
        reminders: Upcoming reminders.
        weather: Weather (uses the default location).
        schedule: Calendar events.
        news: Headlines.
        portfolio: Stock portfolio (only mentioned when you hold stocks).
        clock: Current local time.
    """

    def __init__(
        self,
        *,
        tasks: TaskRepository,
        reminders: ReminderRepository,
        weather: WeatherService | None = None,
        schedule: ScheduleService | None = None,
        news: NewsService | None = None,
        portfolio: PortfolioService | None = None,
        clock: Clock = _local_now,
    ) -> None:
        self._tasks = tasks
        self._reminders = reminders
        self._weather = weather
        self._schedule = schedule
        self._news = news
        self._portfolio = portfolio
        self._clock = clock

    async def facts(self) -> str:
        """A compact, factual summary for the language model to turn into speech."""
        now = self._clock()
        sections = await asyncio.gather(
            self._safe(self._weather_line),
            self._safe(self._schedule_line),
            self._safe(self._tasks_line),
            self._safe(self._reminders_line),
            self._safe(self._portfolio_line),
            self._safe(self._news_line),
        )
        lines = [f"It is {now:%A %d %B}, {_clock_label(now)}."]
        lines += [line for line in sections if line]
        return "\n".join(lines)

    async def _weather_line(self) -> str:
        if self._weather is None or not self._weather.default_location:
            return ""
        report = await self._weather.current()
        if report is None:
            return ""
        high = f", high {report.high_c:.0f}°C" if report.high_c is not None else ""
        conditions = f"{report.description}, {report.temperature_c:.0f}°C{high}"
        return f"Weather in {report.location}: {conditions}."

    async def _schedule_line(self) -> str:
        if self._schedule is None or not self._schedule.configured:
            return ""
        events = await self._schedule.day(0)
        now = self._clock()
        remaining = [e for e in events if e.all_day or e.end > now]
        if not remaining:
            return "Calendar: nothing else scheduled today."
        items = [
            f"{'all day' if e.all_day else _clock_label(e.start)} {e.title}" for e in remaining[:6]
        ]
        return f"Calendar today ({len(remaining)}): " + "; ".join(items) + "."

    async def _tasks_line(self) -> str:
        tasks = await self._tasks.list_all()
        if not tasks:
            return "Tasks: none open."
        return f"Open tasks ({len(tasks)}): " + "; ".join(t.title for t in tasks[:5]) + "."

    async def _reminders_line(self) -> str:
        today = self._clock().date()
        due_today = [
            r for r in await self._reminders.upcoming() if r.due_at.astimezone().date() == today
        ]
        if not due_today:
            return ""
        return (
            "Reminders today: "
            + "; ".join(f"{_clock_label(r.due_at.astimezone())} {r.text}" for r in due_today[:5])
            + "."
        )

    async def _portfolio_line(self) -> str:
        if self._portfolio is None:
            return ""
        overview = await self._portfolio.overview()
        if not overview.holdings:
            return ""
        return describe_portfolio(overview)

    async def _news_line(self) -> str:
        if self._news is None:
            return ""
        headlines = await self._news.headlines(limit=3)
        if not headlines:
            return ""
        return "Top headlines: " + "; ".join(h.title for h in headlines) + "."

    @staticmethod
    async def _safe(section: Callable[[], Awaitable[str]]) -> str:
        try:
            return await section()
        except Exception as exc:
            log.warning("briefing_section_failed", section=section.__name__, error=str(exc))
            return ""


BRIEFING_INSTRUCTION = (
    "Give me my briefing now. Using only these facts, speak a warm, natural briefing of at most "
    "seven sentences: greet me for the time of day, then weather, schedule, tasks and reminders, "
    "my stock portfolio in one sentence, and finish with the headlines in one sentence. "
    "Skip anything missing.\n\nFacts:\n"
)


class BriefingScheduler:
    """Delivers the briefing once a day at the configured time.

    The last delivery date is persisted, so restarting the service doesn't
    repeat it. If nobody is connected at that moment, delivery waits (up to
    three hours) until a client connects.

    Args:
        compose: Turns the facts into the spoken text (normally the brain).
        briefing: Fact gatherer.
        notifier: Broadcasts the announcement.
        store: Remembers the last delivery date.
        briefing_time: Returns "HH:MM", or "" when disabled.
        has_listeners: Whether any client is connected.
        clock: Current local time.
        poll_s: Check interval.
    """

    def __init__(
        self,
        *,
        compose: Callable[[str], Awaitable[str]],
        briefing: BriefingService,
        notifier: Notifier,
        store: PreferenceStore,
        briefing_time: Callable[[], str],
        has_listeners: Callable[[], bool],
        clock: Clock = _local_now,
        poll_s: float = 30.0,
    ) -> None:
        self._compose = compose
        self._briefing = briefing
        self._notifier = notifier
        self._store = store
        self._briefing_time = briefing_time
        self._has_listeners = has_listeners
        self._clock = clock
        self._poll_s = poll_s

    async def due(self) -> bool:
        """Whether a briefing should be delivered right now."""
        target = self._briefing_time()
        if not target or not self._has_listeners():
            return False
        now = self._clock()
        hour, minute = (int(part) for part in target.split(":"))
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if not (scheduled <= now <= scheduled.replace(hour=min(23, hour + 3))):
            return False
        return await self._store.get(LAST_BRIEFING_KEY) != now.date().isoformat()

    async def tick(self) -> bool:
        """Deliver the briefing if due; return whether it was delivered."""
        if not await self.due():
            return False
        await self._store.set(LAST_BRIEFING_KEY, self._clock().date().isoformat())
        text = await self._compose(BRIEFING_INSTRUCTION + await self._briefing.facts())
        await self._notifier.announce("briefing", text)
        log.info("briefing_delivered")
        return True

    async def run(self) -> None:
        """Check forever (cancel the task to stop)."""
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("briefing_tick_failed")
            await asyncio.sleep(self._poll_s)
