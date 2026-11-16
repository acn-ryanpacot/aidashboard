"""Money: debts and bills from spreadsheets, due dates, reminders, tool, REST."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from jarvis_core.adapters.documents.folder_index import FolderDocumentIndex
from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqliteDocumentChunkStore,
    SqlitePreferenceStore,
)
from jarvis_core.api.app import create_app
from jarvis_core.application.briefing import BriefingService
from jarvis_core.application.money import (
    BillReminderScheduler,
    MoneyService,
    Payment,
    describe_money,
    next_monthly,
    parse_due,
    read_sheet,
    reminder_text,
    roll_forward,
)
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.config import Settings
from jarvis_core.container import Container, assemble
from jarvis_core.domain.models import ToolCall
from jarvis_core.domain.records import SheetTable
from tests.fakes import LOCAL, FakeEmbedder, FakeLlm, FakeVad, RecordingNotifier

TODAY = date(2026, 11, 16)  # a Monday


def at(day: date, hour: int = 9) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0).astimezone()


def write_debts(path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Debts"
    sheet.append(["Creditor", "Balance", "Monthly payment", "Rate", "Due day"])
    sheet.append(["BDO card", 52000, 5000, 0.035, 18])
    sheet.append(["Home Credit", 8400, 1400, 0.029, 25])
    sheet.append(["Pag-IBIG loan", 122000, 3100, 0.0625, "5th"])
    sheet.append(["Total", 182400, 9500, None, None])  # must not count twice
    for row in sheet.iter_rows(min_row=2):
        row[1].number_format = '"₱"#,##0.00'
        row[3].number_format = "0.0%"
    workbook.save(str(path))


BILLS = (
    "Bill,Amount due,Due date\n"
    'Meralco,"₱3,210.50",2026-11-20\n'
    "PLDT,PHP 1699,10/25/2026\n"  # last month's date: rolls forward
    "Netflix,549,every 2nd\n"
)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    (root / "money").mkdir(parents=True)
    write_debts(root / "money" / "debts.xlsx")
    (root / "money" / "bills.csv").write_text(BILLS, encoding="utf-8")
    (root / "groceries.csv").write_text("Item,Qty\nRice,2\n", encoding="utf-8")  # ignored
    return root


def library(folder: Path | str) -> FolderDocumentIndex:
    return FolderDocumentIndex(
        folder, SqliteDocumentChunkStore(Database(":memory:")), FakeEmbedder(), rescan_s=0
    )


def service(folder: Path | str, today: date = TODAY) -> MoneyService:
    return MoneyService(library(folder), clock=lambda: at(today), ttl_s=0)


def table(header: tuple[str, ...], *rows: tuple[Any, ...]) -> SheetTable:
    return SheetTable("f.csv", "f", header, tuple(rows))


# ------------------------------------------------------------ due dates


@pytest.mark.parametrize(
    ("cell", "expected", "monthly"),
    [
        ("2026-11-20", date(2026, 11, 20), False),
        ("2026-11-20 00:00:00", date(2026, 11, 20), False),
        ("11/20/2026", date(2026, 11, 20), False),
        ("20/11/2026", date(2026, 11, 20), False),  # day first when month > 12 is impossible
        ("Nov 20", date(2026, 11, 20), False),
        ("20 November 2026", date(2026, 11, 20), False),
        ("Jan 5", date(2027, 1, 5), False),  # no year: the next one
        (18, date(2026, 11, 18), True),
        ("15th", date(2026, 12, 15), True),  # the 15th has passed this month
        ("every 2nd", date(2026, 12, 2), True),
        ("30 of every month", date(2026, 11, 30), True),
    ],
)
def test_parse_due(cell: Any, expected: date, monthly: bool) -> None:
    due = parse_due(cell, TODAY)
    assert due is not None
    assert (due.day, due.monthly) == (expected, monthly)


@pytest.mark.parametrize("cell", [None, "", "soon", 0, 45, 3210.5, "31/31/2026", "Foo 3"])
def test_parse_due_rejects(cell: Any) -> None:
    assert parse_due(cell, TODAY) is None


def test_month_ends_and_rolling_forward() -> None:
    assert next_monthly(31, date(2027, 2, 10)) == date(2027, 2, 28)
    assert next_monthly(31, date(2026, 12, 31)) == date(2026, 12, 31)
    assert next_monthly(5, date(2026, 12, 20)) == date(2027, 1, 5)
    assert roll_forward(date(2026, 1, 31), date(2026, 3, 1)) == date(2026, 3, 31)
    assert roll_forward(date(2026, 11, 20), TODAY) == date(2026, 11, 20)


# ------------------------------------------------------------ sheets


def test_paid_column_keeps_overdue_and_skips_paid_rows() -> None:
    sheet = table(
        ("Bill", "Amount", "Due date", "Paid?"),
        ("Water", "450", "2026-11-10", "no"),
        ("Rent", "15000", "2026-11-05", "yes"),
        ("Gym", "1200", "2026-11-30", None),
    )
    debts, payments, _ = read_sheet(sheet, TODAY)
    assert debts == []
    assert [(p.name, p.days) for p in payments] == [("Water", -6), ("Gym", 14)]


def test_sheets_without_money_columns_are_ignored() -> None:
    assert read_sheet(table(("Item", "Qty"), ("Rice", "2")), TODAY) == ([], [], [])
    assert read_sheet(table(("Bill", "Amount"), ("Meralco", "3210")), TODAY) == ([], [], [])


def test_amount_due_header_is_an_amount_not_a_date() -> None:
    sheet = table(("Bill", "Amount due", "Due"), ("Meralco", "3210.50", "20"))
    [payment] = read_sheet(sheet, TODAY)[1]
    assert (payment.amount, payment.due) == (3210.5, date(2026, 11, 20))


async def test_overview_reads_debts_and_bills(folder: Path) -> None:
    overview = await service(folder).overview()
    assert overview.status == "ok"
    assert overview.currency == "₱"
    assert overview.total_owed == 182400  # the Total row isn't counted
    assert overview.monthly_total == 9500
    assert [d.name for d in overview.debts] == ["Pag-IBIG loan", "BDO card", "Home Credit"]
    assert overview.debts[1].rate == pytest.approx(3.5)
    assert sorted(overview.sources) == ["money/bills.csv", "money/debts.xlsx"]
    assert [(p.name, p.due.isoformat(), p.kind) for p in overview.payments] == [
        ("BDO card", "2026-11-18", "debt"),
        ("Meralco", "2026-11-20", "bill"),
        ("Home Credit", "2026-11-25", "debt"),
        ("PLDT", "2026-11-25", "bill"),
        ("Netflix", "2026-12-02", "bill"),
        ("Pag-IBIG loan", "2026-12-05", "debt"),
    ]
    pldt = next(p for p in overview.payments if p.name == "PLDT")
    assert pldt.recurring and pldt.amount == 1699


async def test_overview_without_folder_or_sheets(tmp_path: Path) -> None:
    assert (await service("").overview()).status == "no_folder"
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    assert (await service(tmp_path).overview()).status == "no_sheets"


# ------------------------------------------------------------ speech


async def test_describe_money(folder: Path) -> None:
    text = describe_money(await service(folder).overview(), 7)
    assert text.splitlines()[:4] == [
        "Payments due in the next 7 days, each with its own amount:",
        "1. BDO card (debt payment): ₱5,000, due on Wednesday.",
        "2. Meralco (bill): ₱3,210.50, due on Friday.",
        "That is 2 payments in total, adding up to ₱8,210.50.",
    ]
    assert "Separately, debts overall: ₱182,400 owed in total across 3 debts." in text
    assert "All debts' monthly payments combined: ₱9,500." in text
    assert "Largest single debt: Pag-IBIG loan, balance ₱122,000." in text
    assert "Home Credit" not in text  # 9 days away


def test_reminder_wording() -> None:
    def payment(days: int, kind: str = "bill") -> Payment:
        due = date.fromordinal(TODAY.toordinal() + days)
        return Payment("Meralco", 3210.5, due, days, kind, False, "bills.csv")  # type: ignore[arg-type]

    assert (
        reminder_text([payment(3)], "₱", TODAY, "Ryan")
        == "Ryan, your Meralco bill of ₱3,210.50 is due in 3 days, on Thursday."
    )
    assert reminder_text([payment(0)], "₱", TODAY, "Ryan").endswith("is due today.")
    assert reminder_text([payment(1, "debt")], "₱", TODAY, "Ryan") == (
        "Ryan, your Meralco payment of ₱3,210.50 is due tomorrow."
    )
    assert "is overdue; it was due 2 days ago" in reminder_text([payment(-2)], "₱", TODAY, "Ryan")
    both = reminder_text([payment(0), payment(2)], "₱", TODAY, "Ryan")
    assert both.startswith("Ryan, 2 payments need attention: Meralco, ₱3,210.50, due today;")


# ------------------------------------------------------------ reminders


async def test_reminders_announce_once_per_stage(folder: Path) -> None:
    notifier = RecordingNotifier()
    store = SqlitePreferenceStore(Database(":memory:"))
    day = [TODAY]
    hour = [9]
    lib = library(folder)
    money = MoneyService(lib, clock=lambda: at(day[0], hour[0]), ttl_s=0)
    listeners = [True]
    scheduler = BillReminderScheduler(
        money,
        notifier,
        store,
        days_ahead=lambda: 3,
        has_listeners=lambda: listeners[0],
        user_name="Ryan",
        clock=lambda: at(day[0], hour[0]),
    )

    listeners[0] = False
    assert await scheduler.tick() == 0  # waits for a window
    listeners[0] = True
    hour[0] = 22
    assert await scheduler.tick() == 0  # not at night
    hour[0] = 9

    assert await scheduler.tick() == 1  # BDO card, due Wednesday (2 days)
    assert notifier.announcements[-1] == (
        "bill",
        "Ryan, your BDO card payment of ₱5,000 is due in 2 days, on Wednesday.",
    )
    assert "money" in notifier.topics
    assert await scheduler.tick() == 0  # not again

    day[0] = date(2026, 11, 17)
    assert await scheduler.tick() == 1  # Meralco now within 3 days
    day[0] = date(2026, 11, 18)
    assert await scheduler.tick() == 1  # BDO card: due today
    assert notifier.announcements[-1][1].endswith("is due today.")
    assert await scheduler.tick() == 0


async def test_reminders_off() -> None:
    scheduler = BillReminderScheduler(
        service(""),
        RecordingNotifier(),
        SqlitePreferenceStore(Database(":memory:")),
        days_ahead=lambda: 0,
        has_listeners=lambda: True,
        user_name="Ryan",
        clock=lambda: at(TODAY),
    )
    assert await scheduler.pending() == []


# ------------------------------------------------------------ tool & briefing


async def test_tool_and_briefing(folder: Path) -> None:
    money = service(folder)
    registry = ToolRegistry()
    registry.extend(builtin.money_tools(money))
    text = await registry.execute(ToolCall("get_bills_and_debts", {"days": "3"}))
    assert (
        "Payments due in the next 3 days" in text and "BDO card" in text and "Meralco" not in text
    )

    class Empty:
        async def list_all(self) -> list[object]:
            return []

        async def upcoming(self) -> list[object]:
            return []

    briefing = BriefingService(
        tasks=Empty(),  # type: ignore[arg-type]
        reminders=Empty(),  # type: ignore[arg-type]
        money=money,
        clock=lambda: at(TODAY),
    )
    facts = await briefing.facts()
    assert "Payments due this week: BDO card, ₱5,000, due on Wednesday" in facts


# ------------------------------------------------------------ REST


@pytest.fixture
def container(folder: Path) -> Container:
    return assemble(
        Settings(tools_enabled=True, documents_dir=str(folder), documents_rescan_s=0),
        llm=FakeLlm([]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
        documents=library(""),
    )


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container=container), client=LOCAL) as test_client:
        yield test_client


def test_money_api(client: TestClient, container: Container) -> None:
    body = client.get("/api/money").json()
    assert body["status"] == "ok"
    assert (body["total_owed"], body["monthly_total"], body["reminder_days"]) == (182400, 9500, 3)
    assert body["debts"][0] == {
        "name": "Pag-IBIG loan",
        "balance": 122000,
        "monthly": 3100,
        "rate": 6.25,
        "file": "money/debts.xlsx",
    }
    assert {p["name"] for p in body["payments"]} >= {"Meralco", "BDO card"}
    assert "get_bills_and_debts" in {spec.name for spec in container.tools.specs()}

    updated = client.put("/api/settings", json={"bill_reminder_days": 7}).json()
    assert updated["values"]["bill_reminder_days"] == 7
    assert client.put("/api/settings", json={"bill_reminder_days": 30}).status_code == 400


def test_money_api_without_document_search() -> None:
    container = assemble(
        Settings(tools_enabled=False),
        llm=FakeLlm([]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
    )
    with TestClient(create_app(container=container), client=LOCAL) as client:
        assert client.get("/api/money").json()["status"] == "disabled"
