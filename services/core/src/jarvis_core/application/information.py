"""Cached access to weather, news and calendar data for widgets, tools and briefings."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from jarvis_core.application.cache import TtlCache
from jarvis_core.domain.ports import CalendarProvider, NewsProvider, WeatherProvider
from jarvis_core.domain.records import CalendarEvent, Headline, WeatherReport

Clock = Callable[[], datetime]


def _local_now() -> datetime:
    return datetime.now().astimezone()


class WeatherService:
    """Current weather with a 10-minute cache and a configurable default place.

    Satisfies :class:`~jarvis_core.domain.ports.WeatherProvider` itself, so it can
    be handed to the weather tool in place of the raw provider.

    Args:
        provider: Underlying weather source.
        default_location: Returns the configured home location ("" if unset).
    """

    def __init__(
        self,
        provider: WeatherProvider,
        default_location: Callable[[], str],
        *,
        ttl_s: float = 600,
    ) -> None:
        self._provider = provider
        self._default_location = default_location
        self._cache: TtlCache[WeatherReport | None] = TtlCache(ttl_s)

    @property
    def default_location(self) -> str:
        """The configured home location."""
        return self._default_location()

    async def current(self, location: str = "") -> WeatherReport | None:
        """Weather at ``location`` (or the default); ``None`` if unknown/unset."""
        place = (location or self._default_location()).strip()
        if not place:
            return None
        return await self._cache.get(place.casefold(), lambda: self._provider.current(place))


class NewsService:
    """Headlines from the configured feeds, cached for 15 minutes.

    Args:
        provider: Feed reader.
        feeds: Returns the configured feed URLs.
    """

    def __init__(
        self, provider: NewsProvider, feeds: Callable[[], list[str]], *, ttl_s: float = 900
    ) -> None:
        self._provider = provider
        self._feeds = feeds
        self._cache: TtlCache[list[Headline]] = TtlCache(ttl_s)

    async def headlines(self, limit: int = 10) -> list[Headline]:
        """Newest headlines across all feeds."""
        feeds = self._feeds()
        if not feeds:
            return []
        items = await self._cache.get(tuple(feeds), lambda: self._provider.headlines(feeds, 30))
        return items[:limit]

    def invalidate(self) -> None:
        """Forget cached headlines (e.g. after the feed list changed)."""
        self._cache.clear()


class ScheduleService:
    """Calendar events from the configured ICS sources, cached for 5 minutes.

    Args:
        provider: ICS reader.
        sources: Returns the configured calendar URLs/paths.
        clock: Current local time.
    """

    def __init__(
        self,
        provider: CalendarProvider,
        sources: Callable[[], list[str]],
        *,
        clock: Clock = _local_now,
        ttl_s: float = 300,
    ) -> None:
        self._provider = provider
        self._sources = sources
        self._clock = clock
        self._cache: TtlCache[list[CalendarEvent]] = TtlCache(ttl_s)

    @property
    def configured(self) -> bool:
        """Whether any calendar source is set."""
        return bool(self._sources())

    async def day(self, offset_days: int = 0) -> list[CalendarEvent]:
        """Events on today (+ ``offset_days``), in local time."""
        midnight = self._clock().replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight + timedelta(days=offset_days)
        return await self.between(start, start + timedelta(days=1))

    async def upcoming(self, days: int = 7) -> list[CalendarEvent]:
        """Events from now until ``days`` ahead (including ones in progress)."""
        now = self._clock()
        events = await self.between(
            now.replace(hour=0, minute=0, second=0, microsecond=0), now + timedelta(days=days)
        )
        return [e for e in events if e.end > now]

    async def between(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        """Events overlapping ``[start, end)``."""
        sources = self._sources()
        if not sources:
            return []
        key = (tuple(sources), start.isoformat(), end.isoformat())
        return await self._cache.get(key, lambda: self._provider.events(sources, start, end))

    def invalidate(self) -> None:
        """Forget cached events."""
        self._cache.clear()
