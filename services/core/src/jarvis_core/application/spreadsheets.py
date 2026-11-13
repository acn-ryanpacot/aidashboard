"""Exact answers from the user's spreadsheets (debts, budgets, bills).

A small local language model is unreliable at adding up a column of numbers,
so the ``read_spreadsheet`` tool does the arithmetic here and hands the model
finished totals, largest and smallest values to read out.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from jarvis_core.domain.records import Cell, SheetTable

#: Headers that hold identifiers, not quantities: never summarised.
_IDENTIFIER = re.compile(
    r"(\b(id|no|nos|number|num|phone|mobile|tel|zip|code|ref|tin|sss)\b|#)",
    re.IGNORECASE,
)
#: Headers whose numbers can be compared but not added up.
_NOT_SUMMABLE = re.compile(
    r"\b(years?|days?|dates?|months?|rates?|apr|percent(age)?|age|rank|terms?)\b|%",
    re.IGNORECASE,
)
_CURRENCY = {"₱": "₱", "php": "₱", "$": "$", "usd": "$", "€": "€", "eur": "€", "£": "£"}
_CURRENCY_PATTERN = re.compile(r"^(₱|php|p(?=\s*\d)|\$|usd|€|eur|£)\s*", re.IGNORECASE)
_NUMBER = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
_WORD = re.compile(r"[a-z0-9]+")
_FILE_NOISE = frozenset({"my", "the", "file", "sheet", "spreadsheet", "excel", "xlsx", "csv"})
MAX_ROWS_SHOWN = 25
MAX_OUTPUT_CHARS = 3500


@dataclass(frozen=True, slots=True)
class Parsed:
    """A cell read as a number.

    Attributes:
        value: The number (percent cells keep their percent value, 3.5 for 3.5%).
        currency: ``₱``, ``$``, … when the cell showed one.
        percent: The cell was written as a percentage.
    """

    value: float
    currency: str | None = None
    percent: bool = False


def parse_number(cell: Cell) -> Parsed | None:
    """Read ``cell`` as a number: ``52000``, ``"₱52,000.50"``, ``"(1,200)"``, ``"3.5%"``.

    Returns:
        The number, or ``None`` for text, dates and empty cells.
    """
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, int | float):
        return Parsed(float(cell))
    text = cell.strip().replace(chr(0xA0), " ")  # non-breaking spaces
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    if text.startswith("-"):
        negative, text = True, text[1:].strip()
    currency = None
    match = _CURRENCY_PATTERN.match(text)
    if match:
        currency = _CURRENCY.get(match.group(1).lower(), "₱")
        text = text[match.end() :]
    percent = text.endswith("%")
    if percent:
        text = text[:-1].strip()
    text = text.replace(",", "").replace(" ", "")
    if not _NUMBER.match(text):
        return None
    value = float(text)
    return Parsed(-value if negative else value, currency, percent)


@dataclass(frozen=True, slots=True)
class ColumnSummary:
    """Totals for one numeric column."""

    name: str
    count: int
    total: float | None
    average: float
    largest: tuple[float, str]
    smallest: tuple[float, str]
    currency: str | None
    percent: bool


def label_column(table: SheetTable) -> int | None:
    """Index of the column that names each row (the first mostly-text column)."""
    for index in range(len(table.header)):
        values = [row[index] for row in table.rows if row[index] not in (None, "")]
        if values and sum(parse_number(v) is None for v in values) * 2 > len(values):
            return index
    return None


def summarize_columns(table: SheetTable, rows: Sequence[tuple[Cell, ...]]) -> list[ColumnSummary]:
    """Totals, averages, largest and smallest for every numeric column."""
    label_at = label_column(table)
    summaries = []
    for index, name in enumerate(table.header):
        if index == label_at or _IDENTIFIER.search(name):
            continue
        filled = [(row, row[index]) for row in rows if row[index] not in (None, "")]
        parsed = [(row, parse_number(value)) for row, value in filled]
        numbers = [(row, p) for row, p in parsed if p is not None]
        if not numbers or len(numbers) * 5 < len(filled) * 3:
            continue  # under 60% numbers: a text column
        values = [p.value for _, p in numbers]
        labels = [_row_label(row, label_at, i) for i, (row, _) in enumerate(numbers)]
        currencies = {p.currency for _, p in numbers if p.currency}
        percent = sum(p.percent for _, p in numbers) * 2 > len(numbers)
        summable = not percent and not _NOT_SUMMABLE.search(name)
        top = max(range(len(values)), key=values.__getitem__)
        bottom = min(range(len(values)), key=values.__getitem__)
        summaries.append(
            ColumnSummary(
                name=name,
                count=len(values),
                total=sum(values) if summable else None,
                average=sum(values) / len(values),
                largest=(values[top], labels[top]),
                smallest=(values[bottom], labels[bottom]),
                currency=currencies.pop() if len(currencies) == 1 else None,
                percent=percent,
            )
        )
    return summaries


def filter_rows(table: SheetTable, text: str) -> list[tuple[Cell, ...]]:
    """Rows containing every word of ``text`` (case-insensitive)."""
    words = _WORD.findall(text.lower())
    if not words:
        return list(table.rows)
    return [
        row
        for row in table.rows
        if all(word in " ".join(str(c) for c in row if c is not None).lower() for word in words)
    ]


def describe_table(table: SheetTable, filter_text: str = "") -> str:
    """A compact, exact summary of a sheet for the model to read out."""
    rows = filter_rows(table, filter_text) if filter_text.strip() else list(table.rows)
    scope = f' matching "{filter_text.strip()}"' if filter_text.strip() else ""
    lines = [
        f'{table.file}, sheet "{table.sheet}": {len(rows)} row(s){scope} '
        f"of {len(table.rows)}. Columns: {', '.join(table.header)}."
    ]
    if not rows:
        return lines[0]
    for column in summarize_columns(table, rows):

        def show(value: float, column: ColumnSummary = column) -> str:
            return format_amount(value, column.currency, column.percent)

        parts = []
        if column.total is not None:
            parts.append(f"total {show(column.total)}")
        if column.count > 1:
            parts += [
                f"largest {show(column.largest[0])} ({column.largest[1]})",
                f"smallest {show(column.smallest[0])} ({column.smallest[1]})",
                f"average {show(column.average)}",
            ]
        elif column.total is None:
            parts.append(f"{show(column.largest[0])} ({column.largest[1]})")
        lines.append(f"{column.name}: {', '.join(parts)}.")
    shown = rows[:MAX_ROWS_SHOWN]
    lines.append("Rows: " + " | ".join(_row_text(table.header, row) for row in shown))
    if len(rows) > len(shown):
        lines.append(f"(and {len(rows) - len(shown)} more rows; the totals above include them)")
    return "\n".join(lines)


def describe_tables(tables: Sequence[SheetTable], filter_text: str = "") -> str:
    """:func:`describe_table` for every sheet, capped for the model's context."""
    text = "\n\n".join(describe_table(table, filter_text) for table in tables)
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[: MAX_OUTPUT_CHARS - 1] + "…"
    return text


def format_amount(value: float, currency: str | None = None, percent: bool = False) -> str:
    """``₱182,400`` / ``3.5%`` / ``1,234.56``: digits the model can read aloud."""
    rounded = round(value, 2)
    text = f"{abs(rounded):,.2f}".removesuffix(".00")
    if "." in text and not currency:
        text = text.rstrip("0")  # money keeps its centavos: ₱4,909.50
    sign = "-" if rounded < 0 else ""
    if percent:
        return f"{sign}{text}%"
    return f"{sign}{currency or ''}{text}"


def match_file(query: str, names: Sequence[str]) -> str | None:
    """The spreadsheet ``query`` refers to (``"debts"`` → ``money/Debts 2026.xlsx``).

    Returns:
        The best match, or ``None`` when nothing shares a word with the query.
    """
    wanted = {w for w in _WORD.findall(query.lower()) if w not in _FILE_NOISE}
    if not wanted:
        return None
    best: tuple[int, int, str] | None = None
    for name in names:
        lowered = name.lower()
        words = set(_WORD.findall(lowered))
        score = sum(
            2 if word in words else 1
            for word in wanted
            if word in words or word in lowered or word.rstrip("s") in lowered
        )
        if score and (best is None or (score, -len(name)) > (best[0], best[1])):
            best = (score, -len(name), name)
    return best[2] if best else None


def _row_label(row: tuple[Cell, ...], label_at: int | None, position: int) -> str:
    if label_at is not None and row[label_at] not in (None, ""):
        return str(row[label_at])
    return f"row {position + 1}"


def _row_text(header: Sequence[str], row: tuple[Cell, ...]) -> str:
    return ", ".join(
        f"{name} {_cell_text(value)}"
        for name, value in zip(header, row, strict=True)
        if value not in (None, "")
    )


def _cell_text(value: Cell) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
