"""Calendars from iCalendar (ICS) feeds — Google, Outlook, Apple or a local file.

Every major calendar service publishes a private ICS address (Google:
*Settings → your calendar → "Secret address in iCal format"*), so reading
your schedule needs no OAuth app, API key or subscription.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any

import httpx
import structlog

from jarvis_core.domain.records import CalendarEvent

log = structlog.get_logger(__name__)


def _local_tz() -> tzinfo:
    zone = datetime.now().astimezone().tzinfo
    assert zone is not None
    return zone


def _as_local(value: date | datetime, zone: tzinfo) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
    return datetime.combine(value, time(), tzinfo=zone)


def parse_ics(
    data: bytes | str,
    start: datetime,
    end: datetime,
    *,
    calendar_name: str = "",
    zone: tzinfo | None = None,
) -> list[CalendarEvent]:
    """Expand the events of one ICS document that overlap ``[start, end)``.

    Recurring events (RRULE, EXDATE, RDATE) are expanded into occurrences.

    Raises:
        ValueError: If ``data`` is not a valid calendar.
    """
    import icalendar
    import recurring_ical_events

    zone = zone or _local_tz()
    try:
        calendar = icalendar.Calendar.from_ical(data)
    except Exception as exc:
        raise ValueError(f"not a valid iCalendar document: {exc}") from exc
    name = str(calendar.get("X-WR-CALNAME", "") or calendar_name)

    events: list[CalendarEvent] = []
    component: Any
    for component in recurring_ical_events.of(calendar).between(start, end):
        raw_start = component.decoded("DTSTART")
        all_day = not isinstance(raw_start, datetime)
        begins = _as_local(raw_start, zone)
        if component.get("DTEND") is not None:
            ends = _as_local(component.decoded("DTEND"), zone)
        elif component.get("DURATION") is not None:
            ends = begins + component.decoded("DURATION")
        else:
            ends = begins + (timedelta(days=1) if all_day else timedelta(0))
        events.append(
            CalendarEvent(
                title=str(component.get("SUMMARY", "")).strip() or "Untitled event",
                start=begins,
                end=ends,
                all_day=all_day,
                location=str(component.get("LOCATION", "") or "").strip(),
                calendar=name,
            )
        )
    return sorted(events, key=lambda e: (e.start, not e.all_day))


class IcsCalendarProvider:
    """Implements :class:`~jarvis_core.domain.ports.CalendarProvider`.

    Sources may be ``https://``/``webcal://`` URLs or paths to ``.ics`` files.
    A failing source is logged and skipped.

    Args:
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=15.0, follow_redirects=True)

    async def events(
        self, sources: Sequence[str], start: datetime, end: datetime
    ) -> list[CalendarEvent]:
        """Occurrences across all ``sources``, soonest first."""
        loaded = await asyncio.gather(*(self._load(s) for s in sources), return_exceptions=True)
        events: list[CalendarEvent] = []
        for source, data in zip(sources, loaded, strict=True):
            if isinstance(data, BaseException):
                log.warning("calendar_failed", source=_redact(source), error=str(data))
                continue
            try:
                events += await asyncio.to_thread(
                    parse_ics, data, start, end, calendar_name=_label(source)
                )
            except ValueError as exc:
                log.warning("calendar_invalid", source=_redact(source), error=str(exc))
        return sorted(events, key=lambda e: (e.start, not e.all_day))

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    async def _load(self, source: str) -> bytes:
        if source.startswith(("http://", "https://", "webcal://")):
            url = (
                "https://" + source[len("webcal://") :]
                if source.startswith("webcal://")
                else source
            )
            response = await self._client.get(url)
            response.raise_for_status()
            return response.content
        return await asyncio.to_thread(_read_file, source)


def _read_file(source: str) -> bytes:
    return Path(source).expanduser().read_bytes()


def _label(source: str) -> str:
    return Path(source).stem if not source.startswith(("http", "webcal")) else ""


def _redact(source: str) -> str:
    """Secret ICS URLs are credentials — never log them in full."""
    if source.startswith(("http://", "https://", "webcal://")):
        return httpx.URL(source.replace("webcal://", "https://", 1)).host + "/…"
    return source
