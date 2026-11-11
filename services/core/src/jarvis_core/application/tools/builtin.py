"""Built-in tools: time, tasks, reminders, timers, memory, weather, knowledge, web, stocks.

Each factory closes over the ports it needs and returns :class:`Tool` objects.
Results are short, factual strings — the model turns them into speech.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from jarvis_core.application.briefing import BriefingService
from jarvis_core.application.information import NewsService, ScheduleService
from jarvis_core.application.memory import MemoryService
from jarvis_core.application.portfolio import (
    PortfolioOverview,
    PortfolioService,
    describe_ideas,
    describe_portfolio,
)
from jarvis_core.application.stock_alerts import StockAlertService, describe_rule
from jarvis_core.application.timers import (
    MAX_ACTIVE_TIMERS,
    end_time,
    parse_duration,
    parse_timer_request,
    remaining_s,
    spoken_duration,
    timer_name,
)
from jarvis_core.application.tools.registry import (
    Tool,
    ToolError,
    number_arg,
    schema,
    text_arg,
)
from jarvis_core.application.tools.timeparse import resolve_due_time, spoken_time
from jarvis_core.domain.errors import DataSourceUnavailableError
from jarvis_core.domain.models import ToolSpec
from jarvis_core.domain.ports import (
    DocumentSearch,
    KnowledgeProvider,
    Notifier,
    ReminderRepository,
    TaskRepository,
    TimerRepository,
    WeatherProvider,
    WebSearchProvider,
)
from jarvis_core.domain.records import Reminder, Task, Timer

Clock = Callable[[], datetime]


def local_now() -> datetime:
    """The current local time, timezone-aware."""
    return datetime.now().astimezone()


def _string(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


# ---------------------------------------------------------------------- time


def time_tools(clock: Clock = local_now) -> list[Tool]:
    """``get_current_time``."""

    async def get_current_time(_: Mapping[str, Any]) -> str:
        now = clock()
        return f"It is {now:%A %d %B %Y}, {now:%H:%M} ({now.tzname()})."

    return [
        Tool(
            ToolSpec(
                "get_current_time",
                "Get the current local date and time. Use for questions about the time or date.",
            ),
            "Checking the time",
            get_current_time,
        )
    ]


# --------------------------------------------------------------------- tasks


def _match_task(tasks: list[Task], reference: str) -> Task:
    """Find a task by numeric id or by (case-insensitive) title fragment."""
    if reference.isdigit():
        for task in tasks:
            if task.id == int(reference):
                return task
    needle = reference.lower()
    matches = [t for t in tasks if needle in t.title.lower()] or [
        t for t in tasks if t.title.lower() in needle
    ]
    if not matches:
        raise ToolError(f"no open task matches '{reference}'")
    if len(matches) > 1:
        titles = "; ".join(t.title for t in matches[:5])
        raise ToolError(f"'{reference}' matches several tasks ({titles}); ask which one")
    return matches[0]


def task_tools(repo: TaskRepository, notifier: Notifier | None = None) -> list[Tool]:
    """``add_task``, ``list_tasks``, ``complete_task``."""

    async def changed() -> None:
        if notifier is not None:
            await notifier.data_changed("tasks")

    async def add_task(args: Mapping[str, Any]) -> str:
        title = text_arg(args, "title")
        assert title is not None
        task = await repo.add(title)
        await changed()
        return f"Added task #{task.id}: {task.title}."

    async def list_tasks(_: Mapping[str, Any]) -> str:
        tasks = await repo.list_all()
        if not tasks:
            return "The task list is empty."
        lines = "; ".join(f"#{t.id} {t.title}" for t in tasks[:15])
        return f"{len(tasks)} open task(s): {lines}."

    async def complete_task(args: Mapping[str, Any]) -> str:
        reference = text_arg(args, "task")
        assert reference is not None
        task = _match_task(await repo.list_all(), reference)
        await repo.set_done(task.id, True)
        await changed()
        return f"Marked '{task.title}' as done."

    return [
        Tool(
            ToolSpec(
                "add_task",
                "Add an item to the user's to-do list.",
                schema({"title": _string("The task, e.g. 'Buy milk'.")}, ["title"]),
            ),
            "Updating your tasks",
            add_task,
        ),
        Tool(
            ToolSpec("list_tasks", "List the user's open to-do items."),
            "Checking your tasks",
            list_tasks,
        ),
        Tool(
            ToolSpec(
                "complete_task",
                "Mark a to-do item as done.",
                schema({"task": _string("Task number or words from its title.")}, ["task"]),
            ),
            "Updating your tasks",
            complete_task,
        ),
    ]


# ----------------------------------------------------------------- reminders


def _match_reminder(reminders: list[Reminder], reference: str) -> Reminder:
    if reference.isdigit():
        for reminder in reminders:
            if reminder.id == int(reference):
                return reminder
    matches = [r for r in reminders if reference.lower() in r.text.lower()]
    if len(matches) != 1:
        raise ToolError(
            f"no upcoming reminder matches '{reference}'"
            if not matches
            else f"'{reference}' matches several reminders; ask which one"
        )
    return matches[0]


def reminder_tools(
    repo: ReminderRepository, notifier: Notifier | None = None, clock: Clock = local_now
) -> list[Tool]:
    """``set_reminder``, ``list_reminders``, ``cancel_reminder``."""

    async def changed() -> None:
        if notifier is not None:
            await notifier.data_changed("reminders")

    async def set_reminder(args: Mapping[str, Any]) -> str:
        text = text_arg(args, "text")
        assert text is not None
        now = clock()
        due = resolve_due_time(
            now, in_minutes=number_arg(args, "in_minutes"), at=text_arg(args, "at", required=False)
        )
        reminder = await repo.add(text, due)
        await changed()
        return f"Reminder #{reminder.id} set for {spoken_time(due, now)}: {reminder.text}."

    async def list_reminders(_: Mapping[str, Any]) -> str:
        now = clock()
        upcoming = await repo.upcoming()
        if not upcoming:
            return "There are no upcoming reminders."
        lines = "; ".join(f"#{r.id} {r.text} ({spoken_time(r.due_at, now)})" for r in upcoming[:10])
        return f"{len(upcoming)} upcoming reminder(s): {lines}."

    async def cancel_reminder(args: Mapping[str, Any]) -> str:
        reference = text_arg(args, "reminder")
        assert reference is not None
        reminder = _match_reminder(await repo.upcoming(), reference)
        await repo.delete(reminder.id)
        await changed()
        return f"Cancelled the reminder '{reminder.text}'."

    return [
        Tool(
            ToolSpec(
                "set_reminder",
                "Schedule a spoken reminder. Give either in_minutes (relative) or at (local time).",
                schema(
                    {
                        "text": _string("What to remind the user about."),
                        "in_minutes": {"type": "number", "description": "Minutes from now."},
                        "at": _string("Local time as YYYY-MM-DDTHH:MM, or HH:MM for the next one."),
                    },
                    ["text"],
                ),
            ),
            "Setting a reminder",
            set_reminder,
        ),
        Tool(
            ToolSpec("list_reminders", "List upcoming reminders."),
            "Checking your reminders",
            list_reminders,
        ),
        Tool(
            ToolSpec(
                "cancel_reminder",
                "Cancel an upcoming reminder.",
                schema({"reminder": _string("Reminder number or words from it.")}, ["reminder"]),
            ),
            "Updating your reminders",
            cancel_reminder,
        ),
    ]


# -------------------------------------------------------------------- timers


def _match_timer(timers: list[Timer], reference: str) -> list[Timer]:
    reference = reference.strip().lower()
    if not reference or reference in ("it", "the timer", "timer", "that"):
        return timers if len(timers) == 1 else []
    if reference in ("all", "all timers", "every timer", "everything"):
        return timers
    if reference.lstrip("#").isdigit():
        return [t for t in timers if t.id == int(reference.lstrip("#"))]
    by_label = [t for t in timers if t.label and reference in t.label.lower()]
    if by_label:
        return by_label
    try:
        seconds = parse_duration(reference)
    except ValueError:
        return []
    return [t for t in timers if t.duration_s == seconds]


def timer_tools(
    repo: TimerRepository, notifier: Notifier | None = None, clock: Clock = local_now
) -> list[Tool]:
    """``set_timer``, ``list_timers``, ``cancel_timer``."""

    async def changed() -> None:
        if notifier is not None:
            await notifier.data_changed("timers")

    async def set_timer(args: Mapping[str, Any]) -> str:
        raw = args.get("duration")
        if isinstance(raw, int | float) and not isinstance(raw, bool):
            raw = f"{raw} minutes"
        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("'duration' is required, e.g. '10 minutes'")
        try:
            seconds, leftover = parse_timer_request(raw)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        label = (text_arg(args, "label", required=False) or leftover).strip()
        if len(await repo.active()) >= MAX_ACTIVE_TIMERS:
            raise ToolError(f"there are already {MAX_ACTIVE_TIMERS} timers running")
        now = clock()
        timer = await repo.add(label, seconds, end_time(now, seconds))
        await changed()
        return (
            f"Started {timer_name(timer)} for {spoken_duration(seconds)}; "
            f"it rings {spoken_time(timer.ends_at, now)}."
        )

    async def list_timers(_: Mapping[str, Any]) -> str:
        now = clock()
        timers = await repo.active()
        if not timers:
            return "No timers are running."
        items = "; ".join(
            f"{timer_name(t)}: {spoken_duration(remaining_s(t, now))} left" for t in timers[:10]
        )
        return f"{len(timers)} timer(s) running: {items}."

    async def cancel_timer(args: Mapping[str, Any]) -> str:
        timers = await repo.active()
        if not timers:
            raise ToolError("no timers are running")
        reference = text_arg(args, "timer", required=False) or ""
        matches = _match_timer(timers, reference)
        if not matches:
            raise ToolError(
                f"no running timer matches '{reference}'"
                if reference
                else "several timers are running; ask which one"
            )
        for timer in matches:
            await repo.delete(timer.id)
        await changed()
        return "Cancelled " + ", ".join(timer_name(t) for t in matches) + "."

    return [
        Tool(
            ToolSpec(
                "set_timer",
                "Start a countdown timer that rings when done, e.g. '10 minutes' for the rice.",
                schema(
                    {
                        "duration": _string("How long, e.g. '10 minutes', '1h30m', '90 seconds'."),
                        "label": _string("Optional name, e.g. 'rice' or 'tea'."),
                    },
                    ["duration"],
                ),
            ),
            "Starting a timer",
            set_timer,
        ),
        Tool(
            ToolSpec("list_timers", "List running timers and the time left on each."),
            "Checking your timers",
            list_timers,
        ),
        Tool(
            ToolSpec(
                "cancel_timer",
                "Stop a running timer.",
                schema({"timer": _string("Its name or duration, or 'all'. Optional if only one.")}),
            ),
            "Stopping the timer",
            cancel_timer,
        ),
    ]


# -------------------------------------------------------------------- memory


def memory_tools(memory: MemoryService, notifier: Notifier | None = None) -> list[Tool]:
    """``remember``, ``recall``, ``forget``."""

    async def changed() -> None:
        if notifier is not None:
            await notifier.data_changed("memories")

    async def remember(args: Mapping[str, Any]) -> str:
        fact = text_arg(args, "fact")
        assert fact is not None
        await memory.remember(fact)
        await changed()
        return f"Stored in long-term memory: {fact}"

    async def recall(args: Mapping[str, Any]) -> str:
        query = text_arg(args, "query")
        assert query is not None
        found = await memory.recall(query, limit=5)
        if not found:
            return "Nothing relevant is stored in memory."
        return "Relevant memories: " + "; ".join(m.record.text for m in found)

    async def forget(args: Mapping[str, Any]) -> str:
        query = text_arg(args, "query")
        assert query is not None
        found = await memory.recall(query, limit=1)
        if not found:
            raise ToolError("no stored memory matches that")
        await memory.forget(found[0].record.id)
        await changed()
        return f"Forgot: {found[0].record.text}"

    return [
        Tool(
            ToolSpec(
                "remember",
                "Save a lasting fact or preference about the user when they ask you to remember "
                "something.",
                schema({"fact": _string("The fact, as a full sentence.")}, ["fact"]),
            ),
            "Committing that to memory",
            remember,
        ),
        Tool(
            ToolSpec(
                "recall",
                "Search long-term memory for facts the user told you before.",
                schema({"query": _string("What to look for.")}, ["query"]),
            ),
            "Searching my memory",
            recall,
        ),
        Tool(
            ToolSpec(
                "forget",
                "Delete a stored memory when the user asks you to forget something.",
                schema({"query": _string("Words describing the memory.")}, ["query"]),
            ),
            "Updating my memory",
            forget,
        ),
    ]


# ------------------------------------------------------------- information


def weather_tools(
    provider: WeatherProvider, default_location: str | Callable[[], str] = ""
) -> list[Tool]:
    """``get_weather``. ``default_location`` may be a callable (live settings)."""
    home = default_location if callable(default_location) else (lambda: default_location)

    async def get_weather(args: Mapping[str, Any]) -> str:
        location = text_arg(args, "location", required=False) or home()
        if not location:
            raise ToolError("no location given and no default location configured; ask the user")
        report = await provider.current(location)
        if report is None:
            raise ToolError(f"could not find a place called '{location}'")
        parts = [
            f"{report.location}: {report.description}, {report.temperature_c:.0f}°C",
            f"feels like {report.feels_like_c:.0f}°C",
            f"humidity {report.humidity_pct:.0f}%",
            f"wind {report.wind_kph:.0f} km/h",
        ]
        if report.high_c is not None and report.low_c is not None:
            parts.append(f"today's high {report.high_c:.0f}°C, low {report.low_c:.0f}°C")
        return ", ".join(parts) + "."

    hint = " Defaults to the user's home location if none is given."
    return [
        Tool(
            ToolSpec(
                "get_weather",
                "Get current weather and today's high/low for a place." + hint,
                schema({"location": _string("City name, e.g. 'London'.")}),
            ),
            "Checking the weather",
            get_weather,
        )
    ]


def knowledge_tools(provider: KnowledgeProvider) -> list[Tool]:
    """``lookup_encyclopedia``."""

    async def lookup(args: Mapping[str, Any]) -> str:
        topic = text_arg(args, "topic")
        assert topic is not None
        article = await provider.lookup(topic)
        if article is None:
            return f"The encyclopedia has no article about '{topic}'."
        return f"{article.title}: {article.summary}"

    return [
        Tool(
            ToolSpec(
                "lookup_encyclopedia",
                "Look up factual background on a person, place, thing or event (Wikipedia).",
                schema({"topic": _string("The subject, e.g. 'Alan Turing'.")}, ["topic"]),
            ),
            "Consulting the encyclopedia",
            lookup,
        )
    ]


def web_search_tools(provider: WebSearchProvider) -> list[Tool]:
    """``web_search``."""

    async def web_search(args: Mapping[str, Any]) -> str:
        query = text_arg(args, "query")
        assert query is not None
        results = await provider.search(query, limit=5)
        if not results:
            return "The web search returned no results."
        return "Search results: " + " | ".join(f"{r.title}: {r.snippet}" for r in results)

    return [
        Tool(
            ToolSpec(
                "web_search",
                "Search the web for current events, news or anything recent.",
                schema({"query": _string("Search terms.")}, ["query"]),
            ),
            "Searching the web",
            web_search,
        )
    ]


def document_tools(search: DocumentSearch) -> list[Tool]:
    """``search_documents``."""

    async def search_documents(args: Mapping[str, Any]) -> str:
        query = text_arg(args, "query")
        assert query is not None
        hits = await search.search(query, limit=4)
        if not hits:
            return "Nothing relevant was found in the user's documents."
        return "Passages from the user's documents: " + " | ".join(
            f"[{hit.path}] {hit.text}" for hit in hits
        )

    return [
        Tool(
            ToolSpec(
                "search_documents",
                "Search the user's own notes and documents for information.",
                schema({"query": _string("What to look for.")}, ["query"]),
            ),
            "Searching your documents",
            search_documents,
        )
    ]


# ------------------------------------------------------------ phase 4 data


def _clock(moment: datetime) -> str:
    return moment.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")


def news_tools(news: NewsService) -> list[Tool]:
    """``get_headlines``."""

    async def get_headlines(args: Mapping[str, Any]) -> str:
        topic = (text_arg(args, "topic", required=False) or "").lower()
        headlines = await news.headlines(limit=30)
        if topic:
            headlines = [h for h in headlines if topic in h.title.lower()]
        if not headlines:
            return "No headlines found" + (f" about {topic}." if topic else ".")
        return "Headlines: " + " | ".join(f"{h.title} ({h.source})" for h in headlines[:6])

    return [
        Tool(
            ToolSpec(
                "get_headlines",
                "Get the latest news headlines from the user's feeds, optionally about a topic.",
                schema({"topic": _string("Optional keyword, e.g. 'football'.")}),
            ),
            "Reading the headlines",
            get_headlines,
        )
    ]


def schedule_tools(schedule: ScheduleService, clock: Clock = local_now) -> list[Tool]:
    """``get_schedule``."""

    async def get_schedule(args: Mapping[str, Any]) -> str:
        if not schedule.configured:
            raise ToolError("no calendar is connected; it can be added in Settings")
        day = (text_arg(args, "day", required=False) or "today").lower()
        offset = {"today": 0, "tomorrow": 1}.get(day)
        if offset is None:
            try:
                target = datetime.fromisoformat(day).date()
            except ValueError as exc:
                raise ToolError("day must be 'today', 'tomorrow' or YYYY-MM-DD") from exc
            offset = (target - clock().date()).days
        events = await schedule.day(offset)
        label = day if day in ("today", "tomorrow") else f"on {day}"
        if not events:
            return f"Nothing is scheduled {label}."
        items = "; ".join(
            f"{'all day' if e.all_day else _clock(e.start)}: {e.title}"
            + (f" at {e.location}" if e.location else "")
            for e in events[:10]
        )
        return f"{len(events)} event(s) {label}: {items}."

    return [
        Tool(
            ToolSpec(
                "get_schedule",
                "Get the user's calendar events for a day.",
                schema({"day": _string("'today', 'tomorrow' or a date YYYY-MM-DD.")}),
            ),
            "Checking your calendar",
            get_schedule,
        )
    ]


def portfolio_tools(portfolio: PortfolioService) -> list[Tool]:
    """``get_portfolio`` and ``get_stock_ideas`` (PSE, from PisoTiyempo)."""

    async def overview() -> PortfolioOverview:
        try:
            return await portfolio.overview()
        except DataSourceUnavailableError as exc:
            raise ToolError(str(exc)) from exc

    async def get_portfolio(_: Mapping[str, Any]) -> str:
        current = await overview()
        text = describe_portfolio(current)
        if not current.holdings:
            text += " " + describe_ideas(current)
        return text

    async def get_stock_ideas(_: Mapping[str, Any]) -> str:
        return describe_ideas(await overview())

    return [
        Tool(
            ToolSpec(
                "get_portfolio",
                "Get how the user's Philippine stock portfolio (PisoTiyempo) did on the latest "
                "trading day: value, day change and the biggest movers.",
            ),
            "Checking your portfolio",
            get_portfolio,
        ),
        Tool(
            ToolSpec(
                "get_stock_ideas",
                "Get up to three PSE stocks that pass a trend-and-value screen, with reasons. "
                "Use when the user asks what stocks to buy or look at.",
            ),
            "Screening PSE stocks",
            get_stock_ideas,
        ),
    ]


def stock_alert_tools(alerts: StockAlertService) -> list[Tool]:
    """``get_stock_alerts`` (the user's PisoTiyempo alerts)."""

    async def get_stock_alerts(_: Mapping[str, Any]) -> str:
        rules = await alerts.rules()
        if not rules:
            return "There are no active PisoTiyempo alerts (they're set in the PisoTiyempo app)."
        triggered = await alerts.triggered()
        fired = {a.rule.uid for a in triggered}
        waiting = [describe_rule(r, spoken=True) for r in rules if r.uid not in fired]
        # Keep the two groups explicit: small models otherwise blur them together.
        parts = [
            f"TRIGGERED at the latest close ({len(triggered)}): "
            + " ".join(a.spoken for a in triggered)
            if triggered
            else f"None of the {len(rules)} PisoTiyempo alerts triggered at the latest close."
        ]
        if waiting:
            parts.append(f"NOT triggered ({len(waiting)}): " + "; ".join(waiting[:12]) + ".")
        return " ".join(parts)

    return [
        Tool(
            ToolSpec(
                "get_stock_alerts",
                "List the user's PisoTiyempo stock alerts and which triggered at the latest close.",
            ),
            "Checking your stock alerts",
            get_stock_alerts,
        )
    ]


def briefing_tools(briefing: BriefingService) -> list[Tool]:
    """``daily_briefing``."""

    async def daily_briefing(_: Mapping[str, Any]) -> str:
        facts = await briefing.facts()
        return (
            "Briefing facts (speak them as a natural briefing of at most seven sentences, "
            f"skipping nothing important):\n{facts}"
        )

    return [
        Tool(
            ToolSpec(
                "daily_briefing",
                "Get everything for a morning briefing: weather, calendar, tasks, reminders and "
                "headlines. Use when the user asks for a briefing or what their day looks like.",
            ),
            "Preparing your briefing",
            daily_briefing,
        )
    ]
