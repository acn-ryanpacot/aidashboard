"""PisoTiyempo stock alerts: reading its database, evaluating, announcing."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import pytest

from jarvis_core.adapters.portfolio.pisotiyempo import PisoTiyempoAlerts
from jarvis_core.application.portfolio import PSE_TIME
from jarvis_core.application.stock_alerts import (
    ANNOUNCED_KEY,
    StockAlertScheduler,
    StockAlertService,
    announcement,
    describe_rule,
    evaluate,
)
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.tools.routing import BUILTIN_GROUPS
from jarvis_core.domain.errors import DataSourceUnavailableError
from jarvis_core.domain.models import ToolCall
from jarvis_core.domain.records import AlertBook, StockAlertRule, StockQuote
from tests.fakes import FixedClock, MemoryPreferences, RecordingNotifier

TUESDAY = date(2026, 11, 10)
EVENING = datetime(2026, 11, 10, 18, 30, tzinfo=PSE_TIME)

# The tables Jarvis reads, as PisoTiyempo's desktop app creates them (Db.kt).
PISO_SCHEMA = """
CREATE TABLE stocks (symbol TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT NOT NULL,
    close REAL NOT NULL, changePct REAL, volume INTEGER NOT NULL, date TEXT NOT NULL,
    source TEXT NOT NULL);
CREATE TABLE analyses (symbol TEXT PRIMARY KEY, name TEXT NOT NULL, sector TEXT NOT NULL,
    asOf TEXT NOT NULL, close REAL NOT NULL, changePct REAL, score INTEGER NOT NULL,
    stance TEXT NOT NULL, topSignal TEXT, rsi14 REAL, aboveSma50 INTEGER, aboveSma200 INTEGER,
    patternNames TEXT NOT NULL, bullishCount INTEGER NOT NULL, bearishCount INTEGER NOT NULL,
    volumeRatio REAL, return3mPct REAL, avgDailyValue REAL NOT NULL, isLiquid INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL);
CREATE TABLE alerts (uid TEXT PRIMARY KEY, symbol TEXT NOT NULL, kind TEXT NOT NULL,
    threshold REAL, active INTEGER NOT NULL, createdAt INTEGER NOT NULL,
    updatedAt INTEGER NOT NULL);
"""


def make_database(path: Path) -> Path:
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(PISO_SCHEMA)
        stocks = [
            ("JFC", 252.4, "2026-11-10"),
            ("ALI", 27.1, "2026-11-10"),
            ("BDO", 151.6, "2026-11-10"),
            ("SM", 900.0, "2026-11-10"),
            ("MER", 520.0, "2026-10-01"),  # stale quote
        ]
        conn.executemany(
            "INSERT INTO stocks VALUES (?, '', '', ?, 0, 1000, ?, 'test')",
            [(s, c, d) for s, c, d in stocks],
        )
        analyses = [
            ("JFC", "2026-11-10", 35, "Bullish engulfing\nVolume surge"),
            ("ALI", "2026-11-10", -40, ""),
            ("BDO", "2026-11-07", 60, ""),  # analysis older than the quote
        ]
        conn.executemany(
            "INSERT INTO analyses VALUES (?, '', '', ?, 0, 0, ?, 'X', NULL, 50, 1, 1, ?, "
            "0, 0, NULL, 0, 0, 1, 0)",
            analyses,
        )
        alerts = [
            ("a1", "JFC", "PRICE_ABOVE", 250.0, 1),
            ("a2", "ALI", "PRICE_BELOW", 28.0, 1),
            ("a3", "JFC", "BUY_SIGNAL", None, 1),
            ("a4", "ALI", "SELL_SIGNAL", None, 1),
            ("a5", "JFC", "PATTERN", None, 1),
            ("a6", "BDO", "BUY_SIGNAL", None, 1),  # analysis not from the quote's day
            ("a7", "SM", "PRICE_ABOVE", 950.0, 1),  # not reached
            ("a8", "MER", "PRICE_ABOVE", 1.0, 1),  # stale
            ("a9", "JFC", "PRICE_BELOW", 1.0, 0),  # inactive
        ]
        conn.executemany(
            "INSERT INTO alerts VALUES (?, ?, ?, ?, ?, 0, 0)",
            alerts,
        )
        conn.commit()
    return path


async def test_database_is_read_read_only(tmp_path: Path) -> None:
    path = make_database(tmp_path / "piso-tiyempo.db")
    before = path.read_bytes()
    book = await PisoTiyempoAlerts(path).alert_book()
    assert [r.uid for r in book.rules] == [f"a{i}" for i in range(1, 9)]  # a9 is inactive
    assert book.quotes["JFC"] == StockQuote(
        "JFC", 252.4, TUESDAY, 35, TUESDAY, ("Bullish engulfing", "Volume surge")
    )
    assert path.read_bytes() == before


async def test_missing_database_and_tables(tmp_path: Path) -> None:
    with pytest.raises(DataSourceUnavailableError):
        await PisoTiyempoAlerts(tmp_path / "missing.db").alert_book()
    empty = tmp_path / "old.db"
    with closing(sqlite3.connect(empty)) as conn:
        conn.execute("CREATE TABLE stocks (symbol TEXT)")
    assert await PisoTiyempoAlerts(empty).alert_book() == AlertBook((), {})


async def test_alert_conditions_match_pisotiyempo(tmp_path: Path) -> None:
    book = await PisoTiyempoAlerts(make_database(tmp_path / "p.db")).alert_book()
    fired = {a.rule.uid: a for a in evaluate(book, TUESDAY)}
    assert sorted(fired) == ["a1", "a2", "a3", "a4", "a5"]
    assert fired["a1"].message == "JFC closed at ₱252.40, above your ₱250.00 alert."
    assert fired["a1"].spoken == "JFC closed at 252.40 pesos, above your 250.00 pesos alert."
    assert fired["a2"].message == "ALI closed at ₱27.10, below your ₱28.00 alert."
    assert fired["a3"].message == "JFC: score +35, technicals now rate it a buy."
    assert fired["a4"].message == "ALI: score -40, technicals now rate it a sell."
    assert fired["a5"].message == "JFC: new pattern, Bullish engulfing, Volume surge."


def test_rule_labels() -> None:
    assert describe_rule(StockAlertRule("x", "JFC", "PRICE_ABOVE", 250)) == "JFC above ₱250.00"
    assert describe_rule(StockAlertRule("y", "ALI", "SELL_SIGNAL", None)) == "ALI turns Sell"


async def test_each_alert_is_announced_once_per_trading_day(tmp_path: Path) -> None:
    path = make_database(tmp_path / "p.db")
    store = MemoryPreferences()
    service = StockAlertService(PisoTiyempoAlerts(path), store, clock=FixedClock(EVENING))
    notifier = RecordingNotifier()
    listening = [False]
    scheduler = StockAlertScheduler(
        service, notifier, has_listeners=lambda: listening[0], user_name="Ryan"
    )

    assert await scheduler.tick() == 0  # nobody listening: keep them for later
    assert notifier.announcements == []

    listening[0] = True
    assert await scheduler.tick() == 5
    kind, text = notifier.announcements[0]
    assert kind == "alert"
    assert text.startswith("Pardon me, Ryan. 5 PisoTiyempo alerts. JFC closed at 252.40 pesos")
    assert notifier.topics == ["portfolio"]
    assert store.data[ANNOUNCED_KEY] == {f"a{i}": "2026-11-10" for i in range(1, 6)}

    assert await scheduler.tick() == 0  # same trading day: not again

    # The next session's close triggers the price alert again.
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("UPDATE stocks SET date = '2026-11-11', close = 255 WHERE symbol = 'JFC'")
        conn.commit()
    assert await scheduler.tick() == 1
    assert notifier.announcements[-1][1] == (
        "Pardon me, Ryan. PisoTiyempo alert: JFC closed at 255.00 pesos, above your 250.00 pesos alert."
    )


def test_long_announcements_are_trimmed() -> None:
    quote = StockQuote("X", 2.0, TUESDAY)
    alerts = evaluate(
        AlertBook(
            tuple(StockAlertRule(str(i), "X", "PRICE_ABOVE", 1.0) for i in range(7)), {"X": quote}
        ),
        TUESDAY,
    )
    assert announcement(alerts, "Ryan").endswith("And 2 more in PisoTiyempo.")


async def test_alert_tool(tmp_path: Path) -> None:
    service = StockAlertService(
        PisoTiyempoAlerts(make_database(tmp_path / "p.db")),
        MemoryPreferences(),
        clock=FixedClock(EVENING),
    )
    registry = ToolRegistry()
    registry.extend(builtin.stock_alert_tools(service))
    text = await registry.execute(ToolCall("get_stock_alerts", {}))
    assert text.startswith("TRIGGERED at the latest close (5): JFC closed at 252.40 pesos")
    assert text.endswith(
        "NOT triggered (3): BDO turns Buy; SM above 950.00 pesos; MER above 1.00 pesos."
    )

    none = StockAlertService(
        PisoTiyempoAlerts(tmp_path / "missing.db"), MemoryPreferences(), clock=FixedClock(EVENING)
    )
    registry = ToolRegistry()
    registry.extend(builtin.stock_alert_tools(none))
    assert "no active PisoTiyempo alerts" in await registry.execute(
        ToolCall("get_stock_alerts", {})
    )


@pytest.mark.parametrize(
    "request_text", ["Did any of my stock alerts trigger?", "what are my alerts in PisoTiyempo"]
)
def test_alert_requests_route_to_the_stock_tools(request_text: str) -> None:
    stocks = next(g for g in BUILTIN_GROUPS if g.name == "stocks")
    assert stocks.matches(request_text)


def test_api_lists_triggered_alerts(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from jarvis_core.adapters.persistence.database import Database
    from jarvis_core.api.app import create_app
    from jarvis_core.config import Settings
    from jarvis_core.container import assemble
    from tests.fakes import FakeLlm, FakePortfolio, FakeVad
    from tests.test_portfolio import snapshot

    path = make_database(tmp_path / "p.db")
    today = datetime.now(PSE_TIME).date().isoformat()  # the container uses the real clock
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("UPDATE stocks SET date = ? WHERE symbol != 'MER'", (today,))
        conn.commit()
    container = assemble(
        Settings(_env_file=None),
        llm=FakeLlm(["ok"]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
        portfolio=FakePortfolio(snapshot()),
        stock_alerts=PisoTiyempoAlerts(path),
    )
    with TestClient(create_app(container=container)) as client:
        alerts = client.get("/api/apps/pisotiyempo").json()["alerts"]
    # Price alerts only: the analyses in the fixture are for another day now.
    assert [(a["symbol"], a["kind"]) for a in alerts] == [
        ("JFC", "PRICE_ABOVE"),
        ("ALI", "PRICE_BELOW"),
    ]
    assert alerts[0]["message"] == "JFC closed at ₱252.40, above your ₱250.00 alert."
