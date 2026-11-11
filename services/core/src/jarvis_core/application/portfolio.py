"""Stock portfolio overview and the "ideas to research" screen.

Data comes from a :class:`~jarvis_core.domain.ports.PortfolioSource` (the
PisoTiyempo app). This module adds what the dashboard and voice need:

* whether the prices are from *today's* session or the last one (PSE time);
* each holding's peso move on the day, biggest movers first;
* up to three **trend-and-value** ideas when the user holds nothing.

The screen is deliberately simple and transparent, so every pick comes with
the reasons it passed (see ``docs/guides/pisotiyempo.md``). PisoTiyempo has
no fundamentals (P/E, dividend yield), so "value" means a reasonable entry
price *within* an uptrend: the stock isn't overbought (RSI) and may have
pulled back below its 50-day average. These are ideas to research, not advice.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from jarvis_core.application.cache import TtlCache
from jarvis_core.domain.ports import PortfolioSource
from jarvis_core.domain.records import (
    PortfolioSnapshot,
    PortfolioSummary,
    StockAnalysis,
    StockHolding,
)

#: Philippine time (no daylight saving), which decides what "today" means for the PSE.
PSE_TIME = timezone(timedelta(hours=8), "PHT")

DISCLAIMER = "Ideas to research, not financial advice."

Clock = Callable[[], datetime]


def _pse_now() -> datetime:
    return datetime.now(PSE_TIME)


# ------------------------------------------------------------------- screen


@dataclass(frozen=True, slots=True)
class IdeaRules:
    """Thresholds of the trend-and-value screen.

    Attributes:
        max_rsi: Highest RSI-14 accepted (above this a stock is "stretched").
        min_score: Lowest source-app score accepted (PisoTiyempo's buy line is +20).
        count: How many ideas to return.
    """

    max_rsi: float = 55.0
    min_score: int = 20
    count: int = 3

    def describe(self) -> str:
        """The rules in one sentence (for empty results and the docs)."""
        return (
            "liquid, above its 200-day average, up over 3 months, "
            f"RSI {self.max_rsi:.0f} or below and a score of +{self.min_score} or more"
        )


@dataclass(frozen=True, slots=True)
class StockIdea:
    """A stock that passed the screen, with the reasons why."""

    analysis: StockAnalysis
    reasons: tuple[str, ...]


def _passes(a: StockAnalysis, rules: IdeaRules) -> bool:
    return (
        a.is_liquid
        and a.above_sma200 is True
        and a.return_3m_pct is not None
        and a.return_3m_pct > 0
        and a.rsi14 is not None
        and a.rsi14 <= rules.max_rsi
        and a.score >= rules.min_score
    )


def idea_reasons(a: StockAnalysis) -> tuple[str, ...]:
    """Plain-language reasons a stock passed the screen."""
    reasons = ["Uptrend (above its 200-day average)"]
    if a.return_3m_pct is not None:
        reasons.append(f"{a.return_3m_pct:+.1f}% over 3 months")
    if a.rsi14 is not None:
        mood = "pulled back" if a.rsi14 < 45 else "not stretched"
        reasons.append(f"RSI {a.rsi14:.0f}, {mood}")
    if a.above_sma50 is False:
        reasons.append("Dipped below its 50-day average")
    reasons.append(f"Score {a.score:+d}")
    return tuple(reasons)


def pick_ideas(
    analyses: Sequence[StockAnalysis], rules: IdeaRules | None = None
) -> list[StockIdea]:
    """The best trend-and-value candidates: highest score first, then lowest RSI."""
    rules = rules or IdeaRules()
    eligible = sorted(
        (a for a in analyses if _passes(a, rules)),
        key=lambda a: (-a.score, a.rsi14 if a.rsi14 is not None else 100.0, a.symbol),
    )
    return [StockIdea(a, idea_reasons(a)) for a in eligible[: rules.count]]


# ----------------------------------------------------------------- overview


@dataclass(frozen=True, slots=True)
class HoldingMove:
    """A holding together with its peso move on the last trading day."""

    holding: StockHolding
    day_change: float


def day_change_value(holding: StockHolding) -> float:
    """Peso change of a position on the day, from its value and % change."""
    if holding.change_pct is None or holding.market_value <= 0 or holding.change_pct <= -100:
        return 0.0
    return holding.market_value - holding.market_value / (1 + holding.change_pct / 100)


def percent_of_previous(summary: PortfolioSummary) -> float | None:
    """The day change as a percentage of yesterday's value."""
    previous = summary.market_value - summary.day_change
    return summary.day_change / previous * 100 if previous > 0 else None


@dataclass(frozen=True, slots=True)
class PortfolioOverview:
    """What the widget, the voice tools and the briefing show.

    Attributes:
        summary: Portfolio totals.
        holdings: Positions, biggest peso movers first.
        ideas: Trend-and-value ideas (computed whether or not you hold stocks).
        session_date: Trading date of the prices.
        is_today: Whether that date is today in Philippine time.
        day_change_pct: Day change in percent of the previous value.
        source: ``feed`` or ``files``.
        rules: The screen that produced ``ideas``.
    """

    summary: PortfolioSummary
    holdings: tuple[HoldingMove, ...]
    ideas: tuple[StockIdea, ...]
    session_date: date | None
    is_today: bool
    day_change_pct: float | None
    source: str
    rules: IdeaRules

    @property
    def session_label(self) -> str:
        """``today (Tue 11 Nov)`` or ``the last session (Mon 10 Nov)``."""
        if self.session_date is None:
            return "the last sync"
        day = f"{self.session_date:%a} {self.session_date.day} {self.session_date:%b}"
        return f"today ({day})" if self.is_today else f"the last session ({day})"


class PortfolioService:
    """Cached portfolio overview for widgets, tools and the briefing.

    Args:
        source: Where holdings and analyses come from.
        clock: Current time (Philippine time by default).
        rules: The ideas screen.
        ttl_s: How long a snapshot is reused.
    """

    def __init__(
        self,
        source: PortfolioSource,
        *,
        clock: Clock = _pse_now,
        rules: IdeaRules | None = None,
        ttl_s: float = 120,
    ) -> None:
        self._source = source
        self._clock = clock
        self._rules = rules or IdeaRules()
        self._cache: TtlCache[PortfolioSnapshot] = TtlCache(ttl_s)

    async def overview(self) -> PortfolioOverview:
        """Current overview.

        Raises:
            DataSourceUnavailableError: If the portfolio app has no data to offer.
        """
        snapshot = await self._cache.get("snapshot", self._source.snapshot)
        moves = sorted(
            (HoldingMove(h, day_change_value(h)) for h in snapshot.holdings),
            key=lambda m: (-abs(m.day_change), m.holding.symbol),
        )
        session = snapshot.summary.as_of
        return PortfolioOverview(
            summary=snapshot.summary,
            holdings=tuple(moves),
            ideas=tuple(pick_ideas(snapshot.analyses, self._rules)),
            session_date=session,
            is_today=session == self._clock().astimezone(PSE_TIME).date(),
            day_change_pct=percent_of_previous(snapshot.summary),
            source=snapshot.source,
            rules=self._rules,
        )

    def invalidate(self) -> None:
        """Forget the cached snapshot (e.g. after the feed address changed)."""
        self._cache.clear()


# ------------------------------------------------------------- spoken text


def pesos(amount: float) -> str:
    """``12,345 pesos`` (rounded; reads naturally aloud)."""
    return f"{abs(amount):,.0f} pesos"


def _move(amount: float, pct: float | None) -> str:
    direction = "up" if amount > 0 else "down" if amount < 0 else "flat"
    if direction == "flat":
        return "flat"
    share = f" {abs(pct):.1f}%" if pct is not None else ""
    return f"{direction}{share} ({pesos(amount)})"


def describe_portfolio(overview: PortfolioOverview) -> str:
    """Facts about the portfolio for the language model to speak."""
    s = overview.summary
    if not overview.holdings:
        return "The PisoTiyempo portfolio has no open positions."
    lines = [
        f"PSE portfolio at the close of {overview.session_label}: worth {pesos(s.market_value)}, "
        f"{_move(s.day_change, overview.day_change_pct)} on the day, and "
        f"{_move(s.unrealized_pnl, s.unrealized_pct)} overall since buying."
    ]
    movers = [
        f"{m.holding.symbol} {m.holding.change_pct:+.1f}% ({pesos(m.day_change)})"
        for m in overview.holdings[:5]
        if m.holding.change_pct is not None
    ]
    if movers:
        lines.append("Biggest moves: " + "; ".join(movers) + ".")
    if not overview.is_today:
        lines.append("Prices are from the last trading session, not today.")
    return " ".join(lines)


def describe_ideas(overview: PortfolioOverview) -> str:
    """The screen's picks (with reasons) for the language model to speak."""
    if not overview.ideas:
        return (
            "No PSE stock passes the trend-and-value screen right now "
            f"({overview.rules.describe()})."
        )
    picks = [
        f"{i}. {idea.analysis.symbol}"
        + (f" ({idea.analysis.name})" if idea.analysis.name else "")
        + ": "
        + ", ".join(idea.reasons)
        for i, idea in enumerate(overview.ideas, start=1)
    ]
    return (
        f"{DISCLAIMER} PSE stocks passing the trend-and-value screen at the close of "
        f"{overview.session_label}: " + " ".join(picks) + ". Always mention that these are "
        "ideas to research, not financial advice."
    )
