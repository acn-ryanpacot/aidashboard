"""Persistent entities and read models owned by the core service.

The core service is the single source of truth for this data; the desktop
widgets and (later) the mobile apps read and write it through the REST API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Task:
    """A to-do item.

    Attributes:
        id: Database id.
        title: What needs doing.
        done: Whether it has been completed.
        created_at: When it was added (timezone-aware).
        completed_at: When it was completed, if it was.
    """

    id: int
    title: str
    done: bool
    created_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Reminder:
    """Something Jarvis should say out loud at a given time.

    Attributes:
        id: Database id.
        text: What to remind the user about.
        due_at: When to deliver it (timezone-aware).
        delivered: Whether it has already been announced.
        created_at: When it was created.
    """

    id: int
    text: str
    due_at: datetime
    delivered: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """A fact Jarvis has been asked to remember long-term.

    Attributes:
        id: Database id.
        text: The fact, in plain language.
        created_at: When it was stored.
    """

    id: int
    text: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StoredMemory:
    """A memory together with its embedding vector (if one was computed)."""

    record: MemoryRecord
    embedding: tuple[float, ...] | None


@dataclass(frozen=True, slots=True)
class ScoredMemory:
    """A memory returned by a similarity search."""

    record: MemoryRecord
    score: float


@dataclass(frozen=True, slots=True)
class WeatherReport:
    """Current conditions at a place.

    Attributes:
        location: Resolved place name, e.g. "Manila, Philippines".
        temperature_c: Air temperature in °C.
        feels_like_c: Apparent temperature in °C.
        description: Human description, e.g. "light rain".
        wind_kph: Wind speed in km/h.
        humidity_pct: Relative humidity in percent.
        high_c: Today's forecast maximum in °C.
        low_c: Today's forecast minimum in °C.
    """

    location: str
    temperature_c: float
    feels_like_c: float
    description: str
    wind_kph: float
    humidity_pct: float
    high_c: float | None = None
    low_c: float | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeArticle:
    """An encyclopedia summary."""

    title: str
    summary: str
    url: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One web search hit."""

    title: str
    snippet: str
    url: str


@dataclass(frozen=True, slots=True)
class DocumentHit:
    """A passage from the user's local documents that matches a query."""

    path: str
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class Headline:
    """A news headline from an RSS/Atom feed."""

    title: str
    source: str
    url: str
    published: datetime | None = None


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """One occurrence of a calendar event (recurrences are expanded).

    Attributes:
        title: Summary line.
        start: Start (timezone-aware; midnight local time for all-day events).
        end: End (timezone-aware).
        all_day: Whether this is a date-only event.
        location: Free-text location, if any.
        calendar: Name of the source calendar.
    """

    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    location: str = ""
    calendar: str = ""


@dataclass(frozen=True, slots=True)
class GpuStatus:
    """Utilisation of one GPU (from ``nvidia-smi``)."""

    name: str
    utilization_pct: float
    memory_used_mb: float
    memory_total_mb: float
    temperature_c: float | None = None


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """A snapshot of the host machine's load."""

    cpu_percent: float
    memory_used_gb: float
    memory_total_gb: float
    gpus: tuple[GpuStatus, ...] = ()
    uptime_s: float = 0.0
