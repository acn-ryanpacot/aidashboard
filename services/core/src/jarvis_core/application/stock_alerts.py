"""Speak the user's PisoTiyempo stock alerts when they trigger.

PisoTiyempo lets the user set alerts per stock (price above/below, score
turns buy/sell, a new pattern). Its phone app checks them after each daily
sync. Jarvis reads the same rules (read-only) and checks them against the
same daily data with the same conditions, so the PC announces what the phone
would notify.

Each alert fires at most once per trading day, like in the app. Jarvis keeps
its own record of what it already announced (in its preferences table),
because it never writes to PisoTiyempo's database.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime

import structlog

from jarvis_core.application.portfolio import PSE_TIME
from jarvis_core.domain.errors import DataSourceUnavailableError
from jarvis_core.domain.ports import Notifier, PreferenceStore, StockAlertSource
from jarvis_core.domain.records import AlertBook, StockAlertRule, StockQuote

log = structlog.get_logger(__name__)

ANNOUNCED_KEY = "pisotiyempo_alerts_announced"

#: PisoTiyempo's score thresholds for "rates it a buy/sell".
BUY_SCORE = 20
SELL_SCORE = -20

#: Quotes older than this are not alerted on (e.g. after a long time off).
MAX_QUOTE_AGE_DAYS = 4

Clock = Callable[[], datetime]


def _pse_now() -> datetime:
    return datetime.now(PSE_TIME)


@dataclass(frozen=True, slots=True)
class FiredAlert:
    """An alert whose condition holds at the latest close.

    Attributes:
        rule: The user's alert.
        quote: The data that triggered it.
        message: For the screen, e.g. "JFC closed at ₱250.20, above your ₱250.00 alert."
        spoken: The same for speech ("250.20 pesos" instead of "₱250.20").
    """

    rule: StockAlertRule
    quote: StockQuote
    message: str
    spoken: str


def _money(amount: float, spoken: bool) -> str:
    return f"{amount:,.2f} pesos" if spoken else f"₱{amount:,.2f}"


def _condition(rule: StockAlertRule, quote: StockQuote, spoken: bool) -> str | None:
    """The alert text if ``rule`` holds for ``quote`` (PisoTiyempo's rules)."""
    sym, threshold = rule.symbol, rule.threshold
    close = _money(quote.close, spoken)
    # Signal alerts need an analysis of that same trading day (as in the app).
    fresh = quote.analysis_date == quote.day
    score = quote.score if fresh else None
    if rule.kind == "PRICE_ABOVE" and threshold is not None and quote.close >= threshold:
        return f"{sym} closed at {close}, above your {_money(threshold, spoken)} alert."
    if rule.kind == "PRICE_BELOW" and threshold is not None and quote.close <= threshold:
        return f"{sym} closed at {close}, below your {_money(threshold, spoken)} alert."
    if rule.kind == "BUY_SIGNAL" and score is not None and score >= BUY_SCORE:
        return f"{sym}: score {score:+d}, technicals now rate it a buy."
    if rule.kind == "SELL_SIGNAL" and score is not None and score <= SELL_SCORE:
        return f"{sym}: score {score:+d}, technicals now rate it a sell."
    if rule.kind == "PATTERN" and fresh and quote.patterns:
        return f"{sym}: new pattern, {', '.join(quote.patterns)}."
    return None


def evaluate(book: AlertBook, today: date) -> list[FiredAlert]:
    """Alerts whose condition holds at each stock's latest (recent) close."""
    fired: list[FiredAlert] = []
    for rule in book.rules:
        quote = book.quotes.get(rule.symbol)
        if quote is None or (today - quote.day).days > MAX_QUOTE_AGE_DAYS:
            continue
        message = _condition(rule, quote, spoken=False)
        if message is not None:
            spoken = _condition(rule, quote, spoken=True) or message
            fired.append(FiredAlert(rule, quote, message, spoken))
    return fired


def describe_rule(rule: StockAlertRule, *, spoken: bool = False) -> str:
    """Short label for an alert rule, e.g. ``JFC above ₱250.00`` or ``BDO turns Buy``."""
    threshold = f" {_money(rule.threshold, spoken)}" if rule.threshold is not None else ""
    return {
        "PRICE_ABOVE": f"{rule.symbol} above{threshold}",
        "PRICE_BELOW": f"{rule.symbol} below{threshold}",
        "BUY_SIGNAL": f"{rule.symbol} turns Buy",
        "SELL_SIGNAL": f"{rule.symbol} turns Sell",
        "PATTERN": f"{rule.symbol} new pattern",
    }.get(rule.kind, f"{rule.symbol} {rule.kind.lower()}")


class StockAlertService:
    """Evaluates the user's alerts and remembers which were announced.

    Args:
        source: Where the alert rules and quotes come from.
        store: Jarvis's preference store (for the "already announced" record).
        clock: Current time (Philippine time by default).
    """

    def __init__(
        self, source: StockAlertSource, store: PreferenceStore, *, clock: Clock = _pse_now
    ) -> None:
        self._source = source
        self._store = store
        self._clock = clock

    def _today(self) -> date:
        return self._clock().astimezone(PSE_TIME).date()

    async def rules(self) -> tuple[StockAlertRule, ...]:
        """The active alert rules (empty if PisoTiyempo's data can't be read)."""
        try:
            return (await self._source.alert_book()).rules
        except DataSourceUnavailableError:
            return ()

    async def triggered(self) -> list[FiredAlert]:
        """Alerts that hold at the latest close (announced or not)."""
        try:
            book = await self._source.alert_book()
        except DataSourceUnavailableError:
            return []
        return evaluate(book, self._today())

    async def pending(self) -> list[FiredAlert]:
        """Triggered alerts not yet announced for their trading day."""
        announced = await self._announced()
        return [a for a in await self.triggered() if announced.get(a.rule.uid) != _day(a)]

    async def mark_announced(self, alerts: list[FiredAlert]) -> None:
        """Remember that ``alerts`` were spoken (one entry per alert, latest day)."""
        announced = await self._announced()
        announced.update({a.rule.uid: _day(a) for a in alerts})
        await self._store.set(ANNOUNCED_KEY, announced)

    async def _announced(self) -> dict[str, str]:
        stored = await self._store.get(ANNOUNCED_KEY)
        return {str(k): str(v) for k, v in stored.items()} if isinstance(stored, dict) else {}


def _day(alert: FiredAlert) -> str:
    return alert.quote.day.isoformat()


def announcement(alerts: list[FiredAlert], user_name: str) -> str:
    """One spoken message for any number of new alerts."""
    if len(alerts) == 1:
        return f"Pardon me, {user_name}. PisoTiyempo alert: {alerts[0].spoken}"
    shown = " ".join(a.spoken for a in alerts[:5])
    more = f" And {len(alerts) - 5} more in PisoTiyempo." if len(alerts) > 5 else ""
    return f"Pardon me, {user_name}. {len(alerts)} PisoTiyempo alerts. {shown}{more}"


class StockAlertScheduler:
    """Checks the alerts every few minutes and announces new ones.

    Announcements wait until a Jarvis window is connected, so an alert that
    triggers while nobody is listening is spoken when you next open Jarvis
    (the same trading day's alerts only).

    Args:
        service: Alert evaluation and bookkeeping.
        notifier: Broadcasts announcements.
        has_listeners: Whether any client is connected.
        user_name: Used to phrase announcements; updated live.
        poll_s: Seconds between checks.
    """

    def __init__(
        self,
        service: StockAlertService,
        notifier: Notifier,
        *,
        has_listeners: Callable[[], bool],
        user_name: str,
        poll_s: float = 300.0,
    ) -> None:
        self._service = service
        self._notifier = notifier
        self._has_listeners = has_listeners
        self.user_name = user_name
        self._poll_s = poll_s

    async def tick(self) -> int:
        """Announce new alerts if someone is listening; return how many."""
        if not self._has_listeners():
            return 0
        pending = await self._service.pending()
        if not pending:
            return 0
        await self._service.mark_announced(pending)
        log.info("stock_alerts_announced", alerts=[a.rule.uid for a in pending])
        await self._notifier.announce("alert", announcement(pending, self.user_name))
        await self._notifier.data_changed("portfolio")
        return len(pending)

    async def run(self) -> None:
        """Check forever (cancel the task to stop)."""
        # A short first delay lets a freshly opened window connect first.
        await asyncio.sleep(min(self._poll_s, 15.0))
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("stock_alert_tick_failed")
            await asyncio.sleep(self._poll_s)
