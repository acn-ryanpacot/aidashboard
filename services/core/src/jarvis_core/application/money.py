"""Debts and bills from the user's own spreadsheets: totals, due dates, reminders.

Jarvis doesn't connect to banks. He reads the spreadsheets in the documents
folder (see :mod:`jarvis_core.adapters.documents.extractors`) and recognises
two kinds of sheet by their column headers:

- **Debts**: a *balance* column (``Balance``, ``Owed``, ``Outstanding``,
  ``Remaining``, ``Principal``…), optionally with a monthly payment, a rate and
  a due day.
- **Bills**: a *due* column (``Due``, ``Due date``, ``Due day``…) and an amount.

Due dates may be full dates (``2026-11-20``, ``11/20/2026``, ``Nov 20``) or a
day of the month (``20``, ``20th``, ``every 15th``) for monthly payments. A
date in the past rolls forward a month at a time (bills recur), unless the
sheet has a ``Paid``/``Status`` column, in which case an unpaid past date is
*overdue* and paid rows are skipped. Rows labelled ``Total`` are ignored so a
totals row isn't counted twice.
"""

from __future__ import annotations

import asyncio
import calendar
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal

import structlog

from jarvis_core.application.cache import TtlCache
from jarvis_core.application.spreadsheets import (
    TOTAL_LABEL,
    format_amount,
    label_column,
    parse_number,
)
from jarvis_core.domain.ports import DocumentLibrary, Notifier, PreferenceStore
from jarvis_core.domain.records import Cell, SheetTable

log = structlog.get_logger(__name__)

#: ``data_changed`` topic for the Money widget.
MONEY_TOPIC = "money"
#: Preference key: which reminders were spoken (``file|name`` → ``due|stage``).
ANNOUNCED_KEY = "bill_reminders_announced"
#: Payments listed up to this many days ahead.
HORIZON_DAYS = 31
#: Used when no cell shows a currency.
DEFAULT_CURRENCY = "₱"
#: Spoken reminders only between these hours (local time).
QUIET_BEFORE, QUIET_AFTER = time(8, 0), time(21, 0)

Clock = Callable[[], datetime]


def _local_now() -> datetime:
    return datetime.now().astimezone()


# ------------------------------------------------------------ columns


_BALANCE = re.compile(
    r"\b(balance|owed?|outstanding|remaining|principal|loan amount|debt|utang|payoff)\b", re.I
)
_MONTHLY = re.compile(
    r"\b(monthly|per month|payments?|amorti[sz]ation|install?ments?|minimum|hulog|emi)\b", re.I
)
_AMOUNT = re.compile(r"\b(amount|amt|bill|cost|price|total|fee|charge|sum)\b", re.I)
_DUE = re.compile(r"\b(due|deadline|pay by|payment date|billing date|cut-?off|day)\b", re.I)
_RATE = re.compile(r"\b(rate|interest|apr)\b|%", re.I)
_PAID = re.compile(r"\b(paid|status|settled|done)\b", re.I)
_PAID_VALUES = frozenset({"yes", "y", "true", "paid", "done", "settled", "x", "✓", "✔", "ok"})


@dataclass(frozen=True, slots=True)
class _Columns:
    label: int | None
    balance: int | None
    monthly: int | None
    amount: int | None
    due: int | None
    rate: int | None
    paid: int | None


def _values(table: SheetTable, index: int) -> list[Cell]:
    return [row[index] for row in table.rows if row[index] not in (None, "")]


def _mostly(values: Sequence[Cell], test: Callable[[Cell], bool]) -> bool:
    return bool(values) and sum(1 for v in values if test(v)) * 5 >= len(values) * 3


def _is_number(value: Cell) -> bool:
    return parse_number(value) is not None


def _find(table: SheetTable, pattern: re.Pattern[str], test: Callable[[Cell], bool],
          skip: set[int]) -> int | None:  # fmt: skip
    for index, name in enumerate(table.header):
        if index not in skip and pattern.search(name) and _mostly(_values(table, index), test):
            return index
    return None


def columns(table: SheetTable, today: date) -> _Columns:
    """Which column holds what, judged by header names *and* the values below them."""
    label = label_column(table)
    used = {label} if label is not None else set()

    def due_like(value: Cell) -> bool:
        return parse_due(value, today) is not None

    due = _find(table, _DUE, due_like, used | set())
    if due is not None:
        used.add(due)
    rate = _find(table, _RATE, _is_number, used)
    if rate is not None:
        used.add(rate)
    monthly = _find(table, _MONTHLY, _is_number, used)
    if monthly is not None:
        used.add(monthly)
    balance = _find(table, _BALANCE, _is_number, used)
    if balance is not None:
        used.add(balance)
    amount = _find(table, _AMOUNT, _is_number, used)
    paid = next((i for i, n in enumerate(table.header) if i not in used and _PAID.search(n)), None)
    return _Columns(label, balance, monthly, amount, due, rate, paid)


# ------------------------------------------------------------ due dates

_MONTHS = {
    name.lower(): number
    for number in range(1, 13)
    for name in (calendar.month_name[number], calendar.month_abbr[number])
}
_MONTHS["sept"] = 9
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
_SLASHED = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})$")
_DAY_ONLY = re.compile(
    r"^(?:every\s+|day\s+|on\s+(?:the\s+)?)?(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s+of\s+(?:the|every|each)\s+month)?$",
    re.IGNORECASE,
)
_MONTH_DAY = re.compile(r"^([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?$", re.I)
_DAY_MONTH = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?(?:,?\s+(\d{4}))?$", re.I)


@dataclass(frozen=True, slots=True)
class Due:
    """A parsed due date.

    Attributes:
        day: The date (for monthly items, the next occurrence on or after today).
        monthly: Given as a day of the month, so it repeats.
        dated: Given as a full calendar date (may be in the past).
    """

    day: date
    monthly: bool = False
    dated: bool = False


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def next_monthly(day_of_month: int, today: date) -> date:
    """The next date (today or later) on ``day_of_month``; the 31st means month end."""
    this_month = _clamped(today.year, today.month, day_of_month)
    if this_month >= today:
        return this_month
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return _clamped(year, month, day_of_month)


def parse_due(cell: Cell, today: date) -> Due | None:
    """Read a due date from a cell: a date, or a day of the month (monthly)."""
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, int | float):
        if float(cell).is_integer() and 1 <= cell <= 31:
            return Due(next_monthly(int(cell), today), monthly=True)
        return None
    text = cell.strip()
    try:
        if match := _ISO.match(text):
            year, month, day = (int(g) for g in match.groups())
            return Due(date(year, month, day), dated=True)
        if match := _SLASHED.match(text):
            first, second, year = (int(g) for g in match.groups())
            year += 2000 if year < 100 else 0
            # Month first (as in the Philippines and the US) unless that's impossible.
            month, day = (second, first) if first > 12 else (first, second)
            return Due(date(year, month, day), dated=True)
        if match := _DAY_ONLY.match(text):
            day = int(match.group(1))
            return Due(next_monthly(day, today), monthly=True) if 1 <= day <= 31 else None
        for pattern, month_at, day_at in ((_MONTH_DAY, 1, 2), (_DAY_MONTH, 2, 1)):
            if match := pattern.match(text):
                named = _MONTHS.get(match.group(month_at).lower())
                if named is None:
                    return None
                month, day = named, int(match.group(day_at))
                if match.group(3):
                    return Due(date(int(match.group(3)), month, day), dated=True)
                when = date(today.year, month, day)
                return Due(when if when >= today else date(today.year + 1, month, day))
    except ValueError:  # 31 February and friends
        return None
    return None


def roll_forward(when: date, today: date) -> date:
    """Move a past date forward a month at a time until it's today or later."""
    day, year, month = when.day, when.year, when.month
    while when < today:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        when = _clamped(year, month, day)
    return when


# ------------------------------------------------------------ read models


@dataclass(frozen=True, slots=True)
class Debt:
    """One row of a debts sheet."""

    name: str
    balance: float
    monthly: float | None
    rate: float | None  # percent, e.g. 3.5
    file: str


@dataclass(frozen=True, slots=True)
class Payment:
    """A bill or debt payment with a due date.

    Attributes:
        days: Days from today (0 = today, negative = overdue).
        kind: ``bill``, or ``debt`` for a debt's monthly payment.
        recurring: Repeats monthly (a day of the month, or a rolled-forward date).
    """

    name: str
    amount: float | None
    due: date
    days: int
    kind: Literal["bill", "debt"]
    recurring: bool
    file: str

    @property
    def uid(self) -> str:
        """Stable identity across days (for announce-once bookkeeping)."""
        return f"{self.file}|{self.name.lower()}"


@dataclass(frozen=True, slots=True)
class MoneyOverview:
    """Everything the Money widget shows."""

    status: Literal["ok", "no_folder", "no_sheets"]
    today: date
    currency: str = DEFAULT_CURRENCY
    debts: tuple[Debt, ...] = ()
    payments: tuple[Payment, ...] = ()
    sources: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_owed(self) -> float:
        """Sum of every debt balance."""
        return sum(d.balance for d in self.debts)

    @property
    def monthly_total(self) -> float:
        """Sum of the debts' monthly payments."""
        return sum(d.monthly or 0.0 for d in self.debts)

    def due_within(self, days: int) -> list[Payment]:
        """Payments due in the next ``days`` days, overdue ones included."""
        return [p for p in self.payments if p.days <= days]


def read_sheet(table: SheetTable, today: date) -> tuple[list[Debt], list[Payment], list[str]]:
    """Debts and dated payments in one sheet, plus the currencies its amounts show."""
    cols = columns(table, today)
    is_debts = cols.balance is not None
    pay_column = (
        cols.monthly if is_debts else (cols.amount if cols.amount is not None else cols.monthly)
    )
    if not is_debts and (cols.due is None or pay_column is None):
        return [], [], []
    debts: list[Debt] = []
    payments: list[Payment] = []
    currencies: list[str] = []
    for position, row in enumerate(table.rows):
        name = _name(row, cols.label, position)
        if TOTAL_LABEL.match(name) or (cols.label is not None and row[cols.label] in (None, "")):
            continue  # a totals row, or a row without a name
        if cols.paid is not None and _is_paid(row[cols.paid]):
            continue
        amount = _amount(row, pay_column, currencies)
        if is_debts:
            balance = _amount(row, cols.balance, currencies)
            if balance is None:
                continue
            debts.append(Debt(name, balance, amount, _rate(row, cols.rate), table.file))
        if cols.due is not None and (due := parse_due(row[cols.due], today)) is not None:
            when, recurring = due.day, due.monthly
            if due.dated and when < today and cols.paid is None:
                when, recurring = roll_forward(when, today), True
            payments.append(
                Payment(
                    name=name,
                    amount=amount,
                    due=when,
                    days=(when - today).days,
                    kind="debt" if is_debts else "bill",
                    recurring=recurring,
                    file=table.file,
                )
            )
    return debts, payments, currencies


def _name(row: tuple[Cell, ...], label: int | None, position: int) -> str:
    if label is not None and row[label] not in (None, ""):
        return str(row[label]).strip()
    return f"Row {position + 1}"


def _amount(row: tuple[Cell, ...], index: int | None, currencies: list[str]) -> float | None:
    if index is None:
        return None
    parsed = parse_number(row[index])
    if parsed is None:
        return None
    if parsed.currency:
        currencies.append(parsed.currency)
    return parsed.value


def _rate(row: tuple[Cell, ...], index: int | None) -> float | None:
    if index is None or (parsed := parse_number(row[index])) is None:
        return None
    # 0.035 without a percent sign is a fraction.
    return parsed.value * 100 if not parsed.percent and 0 < parsed.value < 1 else parsed.value


def _is_paid(cell: Cell) -> bool:
    return str(cell).strip().lower() in _PAID_VALUES if cell is not None else False


# ------------------------------------------------------------ service


class MoneyService:
    """Reads the debts and bills spreadsheets in the documents folder.

    Args:
        library: The documents folder.
        clock: Current local time.
        ttl_s: How long a reading is reused (spreadsheets rarely change).
    """

    def __init__(
        self, library: DocumentLibrary, *, clock: Clock = _local_now, ttl_s: float = 60.0
    ) -> None:
        self._library = library
        self._clock = clock
        self._cache: TtlCache[MoneyOverview] = TtlCache(ttl_s)

    def invalidate(self) -> None:
        """Forget the cached reading (the folder changed)."""
        self._cache.clear()

    async def overview(self) -> MoneyOverview:
        """Debts and upcoming payments (cached for a minute)."""
        today = self._clock().date()
        return await self._cache.get(today, lambda: self._read(today))

    async def _read(self, today: date) -> MoneyOverview:
        if not self._library.folder:
            return MoneyOverview(status="no_folder", today=today)
        debts: list[Debt] = []
        payments: list[Payment] = []
        currencies: list[str] = []
        sources: list[str] = []
        names = await self._library.spreadsheets()
        results = await asyncio.gather(
            *(self._library.tables(name) for name in names), return_exceptions=True
        )
        for name, tables in zip(names, results, strict=True):
            if isinstance(tables, BaseException):
                log.info("money_sheet_unreadable", file=name, reason=str(tables))
                continue
            for table in tables:
                sheet_debts, sheet_payments, sheet_currencies = read_sheet(table, today)
                if sheet_debts or sheet_payments:
                    sources.append(name if len(tables) == 1 else f"{name} ({table.sheet})")
                debts += sheet_debts
                payments += sheet_payments
                currencies += sheet_currencies
        if not sources:
            return MoneyOverview(status="no_sheets", today=today)
        debts.sort(key=lambda d: -d.balance)
        payments = [p for p in payments if p.days <= HORIZON_DAYS]
        payments.sort(key=lambda p: (p.due, p.name.lower()))
        currency = Counter(currencies).most_common(1)[0][0] if currencies else DEFAULT_CURRENCY
        return MoneyOverview(
            status="ok",
            today=today,
            currency=currency,
            debts=tuple(debts),
            payments=tuple(payments),
            sources=tuple(sources),
        )


# ------------------------------------------------------------ speech


def when_text(payment: Payment, today: date) -> str:
    """``today`` / ``tomorrow`` / ``on Thursday`` / ``on Friday 28 November`` / ``3 days ago``."""
    if payment.days < 0:
        late = -payment.days
        return "yesterday" if late == 1 else f"{late} days ago"
    if payment.days == 0:
        return "today"
    if payment.days == 1:
        return "tomorrow"
    if payment.days < 7:
        return f"on {payment.due:%A}"
    return f"on {payment.due:%A} {payment.due.day} {payment.due:%B}"


def payment_text(payment: Payment, currency: str, today: date) -> str:
    """``Meralco, ₱3,210.50, due on Thursday``."""
    amount = f", {format_amount(payment.amount, currency)}" if payment.amount is not None else ""
    verb = "was due" if payment.days < 0 else "due"
    return f"{payment.name}{amount}, {verb} {when_text(payment, today)}"


def describe_money(overview: MoneyOverview, days: int = 14) -> str:
    """Tool output: debts summary and the payments due in the next ``days`` days."""
    if overview.status == "no_folder":
        return "No documents folder is set, so there are no bills or debts to read."
    if overview.status == "no_sheets":
        return (
            "No debts or bills spreadsheet was found in the documents folder. A debts sheet "
            "needs a Balance column; a bills sheet needs Due and Amount columns."
        )
    c, today = overview.currency, overview.today
    # One item per line with its own amount, and the sum last and labelled: small
    # models otherwise attach a bracketed total to the first item.
    lines = []
    upcoming = overview.due_within(days)
    if upcoming:
        lines.append(f"Payments due in the next {days} days, each with its own amount:")
        for number, p in enumerate(upcoming, start=1):
            what = "debt payment" if p.kind == "debt" else "bill"
            amount = format_amount(p.amount, c) if p.amount is not None else "amount unknown"
            state = "OVERDUE, was due" if p.days < 0 else "due"
            lines.append(f"{number}. {p.name} ({what}): {amount}, {state} {when_text(p, today)}.")
        total = sum(p.amount or 0 for p in upcoming)
        count = "1 payment" if len(upcoming) == 1 else f"{len(upcoming)} payments"
        lines.append(f"That is {count} in total, adding up to {format_amount(total, c)}.")
    elif overview.payments:
        later = overview.payments[0]
        lines.append(
            f"Nothing is due in the next {days} days; the next payment is "
            f"{payment_text(later, c, today)}."
        )
    else:
        lines.append("No due dates were found in the spreadsheets.")
    if overview.debts:
        biggest = overview.debts[0]
        lines.append(
            f"Separately, debts overall: {format_amount(overview.total_owed, c)} owed in total "
            f"across {len(overview.debts)} debts."
        )
        if overview.monthly_total:
            lines.append(
                f"All debts' monthly payments combined: {format_amount(overview.monthly_total, c)}."
            )
        lines.append(
            f"Largest single debt: {biggest.name}, balance {format_amount(biggest.balance, c)}."
        )
    lines.append(f"Source files: {', '.join(overview.sources)}.")
    return "\n".join(lines)


def reminder_text(payments: Sequence[Payment], currency: str, today: date, user: str) -> str:
    """One spoken reminder for any number of payments."""
    if len(payments) == 1:
        p = payments[0]
        what = f"{p.name} {'payment' if p.kind == 'debt' else 'bill'}"
        amount = f" of {format_amount(p.amount, currency)}" if p.amount is not None else ""
        if p.days < 0:
            return f"{user}, your {what}{amount} is overdue; it was due {when_text(p, today)}."
        days = f"in {p.days} days, " if p.days > 1 else ""
        return f"{user}, your {what}{amount} is due {days}{when_text(p, today)}."
    items = "; ".join(payment_text(p, currency, today) for p in payments[:6])
    return f"{user}, {len(payments)} payments need attention: {items}."


# ------------------------------------------------------------ reminders


class BillReminderScheduler:
    """Speaks a reminder when a bill or debt payment comes due.

    Each payment is announced at most twice per due date: once when it first
    falls within the reminder window (e.g. three days before) and again on the
    day itself. Overdue unpaid items are announced once. Reminders wait for an
    open Jarvis window and are only spoken between 8 AM and 9 PM.

    Args:
        money: Where payments come from.
        notifier: Broadcasts announcements.
        store: Remembers what was announced.
        days_ahead: The reminder window in days (0 = off); read live.
        has_listeners: Whether any client is connected.
        user_name: Used to phrase reminders; updated live.
        poll_s: Seconds between checks.
        clock: Current local time.
    """

    def __init__(
        self,
        money: MoneyService,
        notifier: Notifier,
        store: PreferenceStore,
        *,
        days_ahead: Callable[[], int],
        has_listeners: Callable[[], bool],
        user_name: str,
        poll_s: float = 1800.0,
        clock: Clock = _local_now,
    ) -> None:
        self._money = money
        self._notifier = notifier
        self._store = store
        self._days_ahead = days_ahead
        self._has_listeners = has_listeners
        self.user_name = user_name
        self._poll_s = poll_s
        self._clock = clock

    async def pending(self) -> list[tuple[Payment, str]]:
        """Payments to announce now, with their stage (``soon``, ``today``, ``overdue``)."""
        window = self._days_ahead()
        if window <= 0:
            return []
        overview = await self._money.overview()
        announced = await self._announced()
        due = []
        for payment in overview.due_within(window):
            stage = "overdue" if payment.days < 0 else "today" if payment.days == 0 else "soon"
            if announced.get(payment.uid) != f"{payment.due.isoformat()}|{stage}":
                due.append((payment, stage))
        return due

    async def tick(self) -> int:
        """Announce what's due if someone is listening at a decent hour; return how many."""
        now = self._clock()
        if not (QUIET_BEFORE <= now.time() < QUIET_AFTER) or not self._has_listeners():
            return 0
        pending = await self.pending()
        if not pending:
            return 0
        overview = await self._money.overview()
        payments = [payment for payment, _ in pending]
        announced = await self._announced()
        announced.update({p.uid: f"{p.due.isoformat()}|{stage}" for p, stage in pending})
        await self._store.set(ANNOUNCED_KEY, announced)
        log.info("bill_reminders_announced", payments=[p.uid for p in payments])
        text = reminder_text(payments, overview.currency, overview.today, self.user_name)
        await self._notifier.announce("bill", text)
        await self._notifier.data_changed(MONEY_TOPIC)
        return len(payments)

    async def run(self) -> None:
        """Check forever (cancel the task to stop)."""
        await asyncio.sleep(min(self._poll_s, 20.0))  # let a window connect first
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("bill_reminder_tick_failed")
            await asyncio.sleep(self._poll_s)

    async def _announced(self) -> dict[str, str]:
        stored = await self._store.get(ANNOUNCED_KEY)
        return {str(k): str(v) for k, v in stored.items()} if isinstance(stored, dict) else {}
