"""Persistent entities and read models owned by the core service.

The core service is the single source of truth for this data; the desktop
widgets and (later) the mobile apps read and write it through the REST API.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


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
class Timer:
    """A countdown that Jarvis announces when it reaches zero.

    Attributes:
        id: Database id.
        label: What it's for, e.g. "rice" ("" if unnamed).
        duration_s: Total length in seconds.
        ends_at: When it rings (timezone-aware).
        created_at: When it was started.
        done: Whether it has rung.
    """

    id: int
    label: str
    duration_s: int
    ends_at: datetime
    created_at: datetime
    done: bool = False


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    """A device (e.g. a phone) allowed to use Jarvis remotely.

    Only a hash of its token is stored; the token itself is shown once.

    Attributes:
        id: Database id.
        name: What the user called it, e.g. "Ryan's phone".
        created_at: When it was paired.
        last_used_at: When it last made a request, if ever.
    """

    id: int
    name: str
    created_at: datetime
    last_used_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class RemoteAccessStatus:
    """Whether phones can reach this PC through Tailscale.

    Attributes:
        installed: The Tailscale CLI was found.
        running: Logged in and connected to the tailnet.
        dns_name: This PC's MagicDNS name, e.g. ``jarvis-pc.tail1234.ts.net``.
        public_url: The HTTPS address ``tailscale serve`` publishes for Jarvis, if any.
    """

    installed: bool
    running: bool = False
    dns_name: str = ""
    public_url: str = ""


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


# --------------------------------------------------------------- portfolio
#
# Read models for stock portfolios kept in a companion app (PisoTiyempo).
# Amounts are in the market's currency (pesos for the PSE); percentages are
# in percent (``1.5`` means +1.5 %), matching the source app.


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    """Totals for the whole (real-money) portfolio.

    Attributes:
        as_of: Trading date of the prices used, if known.
        market_value: Current value of all holdings.
        cost_basis: What the holdings cost.
        unrealized_pnl: ``market_value - cost_basis``.
        unrealized_pct: Unrealized P/L in percent of the cost basis.
        day_change: Value change on the last trading day.
        holdings: Number of positions.
    """

    as_of: date | None
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pct: float
    day_change: float
    holdings: int


@dataclass(frozen=True, slots=True)
class StockHolding:
    """One position.

    Attributes:
        symbol: Ticker, e.g. ``JFC``.
        sector: Sector name ("" if unknown).
        shares: Number of shares held.
        avg_cost: Average cost per share.
        last_price: Latest close, if known.
        change_pct: Change on the last trading day, in percent.
        market_value: ``shares * last_price``.
        unrealized_pnl: Unrealized profit or loss.
        unrealized_pct: Unrealized P/L in percent.
    """

    symbol: str
    sector: str
    shares: int
    avg_cost: float
    last_price: float | None
    change_pct: float | None
    market_value: float
    unrealized_pnl: float
    unrealized_pct: float


@dataclass(frozen=True, slots=True)
class StockAnalysis:
    """The source app's daily technical read of one stock.

    Attributes:
        symbol: Ticker.
        name: Company name.
        sector: Sector name.
        close: Latest close.
        change_pct: Change on the last trading day, in percent.
        score: Composite score from -100 (weak) to +100 (strong).
        stance: The app's label, e.g. ``BUY`` or ``HOLD``.
        rsi14: 14-day relative strength index (0-100).
        above_sma50: Whether the close is above the 50-day average.
        above_sma200: Whether the close is above the 200-day average.
        return_3m_pct: Three-month return in percent.
        is_liquid: Whether it trades enough to enter and exit easily.
    """

    symbol: str
    name: str
    sector: str
    close: float
    change_pct: float | None
    score: int
    stance: str
    rsi14: float | None
    above_sma50: bool | None
    above_sma200: bool | None
    return_3m_pct: float | None
    is_liquid: bool


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Everything read from the portfolio app in one go.

    Attributes:
        summary: Portfolio totals.
        holdings: Open positions.
        analyses: Daily analyses of the stocks the app tracks.
        source: How it was read, e.g. ``feed`` (live API) or ``files`` (export).
    """

    summary: PortfolioSummary
    holdings: tuple[StockHolding, ...]
    analyses: tuple[StockAnalysis, ...]
    source: str


@dataclass(frozen=True, slots=True)
class StockAlertRule:
    """An alert the user set in the portfolio app.

    Attributes:
        uid: The app's id for it.
        symbol: Ticker.
        kind: ``PRICE_ABOVE``, ``PRICE_BELOW``, ``BUY_SIGNAL``, ``SELL_SIGNAL`` or ``PATTERN``.
        threshold: Price threshold for the price kinds.
    """

    uid: str
    symbol: str
    kind: str
    threshold: float | None


@dataclass(frozen=True, slots=True)
class StockQuote:
    """The latest close of a stock, with that day's analysis if there is one.

    Attributes:
        symbol: Ticker.
        close: Closing price.
        day: Trading date of ``close``.
        score: Analysis score (-100 to +100), if analysed.
        analysis_date: Date the analysis is for.
        patterns: Chart/candlestick patterns detected in that analysis.
    """

    symbol: str
    close: float
    day: date
    score: int | None = None
    analysis_date: date | None = None
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AlertBook:
    """Active alert rules and the quotes needed to check them."""

    rules: tuple[StockAlertRule, ...]
    quotes: dict[str, StockQuote]
