"""PisoTiyempo portfolio: adapter, trend-and-value screen, tools, briefing and API."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from jarvis_core.adapters.persistence.database import Database
from jarvis_core.adapters.persistence.repositories import (
    SqliteReminderRepository,
    SqliteTaskRepository,
)
from jarvis_core.adapters.portfolio.pisotiyempo import PisoTiyempoPortfolio, build_snapshot
from jarvis_core.api.app import create_app
from jarvis_core.application.briefing import BriefingService
from jarvis_core.application.portfolio import (
    PSE_TIME,
    IdeaRules,
    PortfolioService,
    day_change_value,
    describe_ideas,
    describe_portfolio,
    pick_ideas,
)
from jarvis_core.application.tools import builtin
from jarvis_core.application.tools.registry import ToolRegistry
from jarvis_core.application.tools.routing import BUILTIN_GROUPS
from jarvis_core.config import Settings
from jarvis_core.container import Container, assemble
from jarvis_core.doctor import Status, check_pisotiyempo
from jarvis_core.domain.errors import DataSourceUnavailableError
from jarvis_core.domain.models import ToolCall
from jarvis_core.domain.records import PortfolioSnapshot, StockHolding
from tests.fakes import FakeLlm, FakePortfolio, FakeVad, FixedClock

TUESDAY = datetime(2026, 11, 10, 18, 30, tzinfo=PSE_TIME)

# Shapes copied from PisoTiyempo's DashboardFeed (camelCase, percent units).
SUMMARY: dict[str, Any] = {
    "asOf": "2026-11-10",
    "marketValue": 101_500.0,
    "costBasis": 95_000.0,
    "unrealizedPnl": 6_500.0,
    "unrealizedPct": 6.84,
    "realizedPnl": 1_200.0,
    "dayChange": 1_500.0,
    "dividendsReceived": 300.0,
    "holdings": 2,
    "sectorWeights": {"Services": 0.6, "Holding Firms": 0.4},
    "warnings": [],
    "practiceValue": 100_000.0,
    "practiceCash": 100_000.0,
}
HOLDINGS: list[dict[str, Any]] = [
    {
        "symbol": "JFC",
        "sector": "Services",
        "shares": 200,
        "avgCost": 250.0,
        "costBasis": 50_000.0,
        "lastPrice": 306.0,
        "changePct": 2.0,
        "marketValue": 61_200.0,
        "unrealizedPnl": 11_200.0,
        "unrealizedPct": 22.4,
    },
    {
        "symbol": "SM",
        "sector": "Holding Firms",
        "shares": 50,
        "avgCost": 900.0,
        "costBasis": 45_000.0,
        "lastPrice": 806.0,
        "changePct": -0.5,
        "marketValue": 40_300.0,
        "unrealizedPnl": -4_700.0,
        "unrealizedPct": -10.44,
    },
]


def analysis(symbol: str, **overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "sector": "Industrial",
        "close": 10.0,
        "changePct": 0.5,
        "score": 50,
        "stance": "BUY",
        "rsi14": 50.0,
        "aboveSma50": True,
        "aboveSma200": True,
        "patterns": [],
        "return3mPct": 8.0,
        "isLiquid": True,
    }
    row.update(overrides)
    return row


ANALYSES = [
    analysis("AAA", score=70, rsi14=48.0),
    analysis("BBB", score=70, rsi14=40.0, aboveSma50=False),  # same score, lower RSI → first
    analysis("CCC", score=30),
    analysis("DDD", score=90, rsi14=72.0),  # stretched
    analysis("EEE", score=80, aboveSma200=False),  # no long-term uptrend
    analysis("FFF", score=80, isLiquid=False),  # illiquid
    analysis("GGG", score=80, return3mPct=-2.0),  # falling
    analysis("HHH", score=10),  # below the buy line
    analysis("III", score=25),  # 4th eligible: cut by count
]


def snapshot(holdings: list[dict[str, Any]] = HOLDINGS) -> PortfolioSnapshot:
    summary = SUMMARY if holdings else {**SUMMARY, "marketValue": 0, "dayChange": 0, "holdings": 0}
    return build_snapshot(summary, holdings, ANALYSES, "feed")


# ------------------------------------------------------------------ adapter


def feed_transport(calls: list[str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.url.path}?{request.url.query.decode()}".rstrip("?"))
        body = {
            "/api/summary": SUMMARY,
            "/api/holdings": HOLDINGS,
            "/api/analyses": ANALYSES,
        }.get(request.url.path)
        return httpx.Response(404) if body is None else httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


def csv_value(value: Any) -> Any:
    """How PisoTiyempo's export writes a value: true/false, lists joined by "; "."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, list):
        return "; ".join(value)
    return value


def write_export(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "summary.json").write_text(json.dumps(SUMMARY), encoding="utf-8")
    for name, rows in (("holdings.csv", HOLDINGS), ("analyses.csv", ANALYSES)):
        with (folder / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows({k: csv_value(v) for k, v in row.items()} for row in rows)


async def test_feed_is_read_from_the_real_account(tmp_path: Path) -> None:
    calls: list[str] = []
    source = PisoTiyempoPortfolio(
        "http://127.0.0.1:8766/",
        tmp_path,
        client=httpx.AsyncClient(transport=feed_transport(calls)),
    )
    snap = await source.snapshot()
    assert snap.source == "feed"
    assert "/api/holdings?account=REAL" in calls
    assert snap.summary.as_of == date(2026, 11, 10)
    assert snap.summary.day_change == 1_500.0
    assert [h.symbol for h in snap.holdings] == ["JFC", "SM"]
    assert snap.holdings[0].change_pct == 2.0
    bbb = next(a for a in snap.analyses if a.symbol == "BBB")
    assert bbb.above_sma50 is False and bbb.is_liquid and bbb.rsi14 == 40.0


async def test_export_files_are_used_when_the_app_is_closed(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    write_export(tmp_path)
    source = PisoTiyempoPortfolio(
        "http://127.0.0.1:8766",
        tmp_path,
        client=httpx.AsyncClient(transport=httpx.MockTransport(refuse)),
    )
    snap = await source.snapshot()
    assert snap.source == "files"
    assert [h.symbol for h in snap.holdings] == ["JFC", "SM"]
    assert snap.holdings[1].shares == 50 and snap.holdings[1].change_pct == -0.5
    fff = next(a for a in snap.analyses if a.symbol == "FFF")
    assert fff.is_liquid is False and fff.above_sma200 is True
    # The files give the same result as the live feed.
    live = build_snapshot(SUMMARY, HOLDINGS, ANALYSES, "files")
    assert snap == live


async def test_files_only_mode_and_missing_data(tmp_path: Path) -> None:
    source = PisoTiyempoPortfolio("", tmp_path / "nowhere")
    with pytest.raises(DataSourceUnavailableError, match="PisoTiyempo"):
        await source.snapshot()
    write_export(tmp_path / "nowhere")
    assert (await source.snapshot()).source == "files"
    await source.aclose()


def test_parsing_tolerates_blanks_and_drops_empty_positions() -> None:
    snap = build_snapshot(
        {"asOf": "", "marketValue": ""},
        [
            {"symbol": "jfc", "shares": "10", "lastPrice": "", "changePct": ""},
            {"symbol": "OLD", "shares": "0"},
        ],
        [{"symbol": "x", "score": "12", "rsi14": "n/a", "aboveSma200": "", "isLiquid": "true"}],
        "files",
    )
    assert snap.summary.as_of is None and snap.summary.market_value == 0.0
    assert [(h.symbol, h.last_price, h.change_pct) for h in snap.holdings] == [("JFC", None, None)]
    a = snap.analyses[0]
    assert (a.symbol, a.score, a.rsi14, a.above_sma200, a.is_liquid) == ("X", 12, None, None, True)


# ------------------------------------------------------------------- screen


def test_trend_and_value_screen() -> None:
    ideas = pick_ideas(snapshot().analyses)
    assert [i.analysis.symbol for i in ideas] == ["BBB", "AAA", "CCC"]
    assert ideas[0].reasons == (
        "Uptrend (above its 200-day average)",
        "+8.0% over 3 months",
        "RSI 40, pulled back",
        "Dipped below its 50-day average",
        "Score +70",
    )
    assert "RSI 48, not stretched" in ideas[1].reasons


def test_screen_thresholds_are_configurable() -> None:
    analyses = snapshot().analyses
    assert [i.analysis.symbol for i in pick_ideas(analyses, IdeaRules(max_rsi=75, count=1))] == [
        "DDD"
    ]
    assert pick_ideas(analyses, IdeaRules(min_score=95)) == []


def test_day_change_of_a_position() -> None:
    holding = StockHolding("JFC", "", 200, 250.0, 306.0, 2.0, 61_200.0, 0.0, 0.0)
    assert day_change_value(holding) == pytest.approx(1_200.0)
    flat = StockHolding("X", "", 1, 1.0, None, None, 10.0, 0.0, 0.0)
    assert day_change_value(flat) == 0.0


# ----------------------------------------------------------------- overview


async def test_overview_sorts_movers_and_labels_the_session() -> None:
    clock = FixedClock(TUESDAY)
    source = FakePortfolio(snapshot())
    service = PortfolioService(source, clock=clock)

    overview = await service.overview()
    assert overview.is_today and overview.session_label == "today (Tue 10 Nov)"
    assert [m.holding.symbol for m in overview.holdings] == ["JFC", "SM"]
    assert overview.holdings[0].day_change == pytest.approx(1_200.0)
    assert overview.day_change_pct == pytest.approx(1_500 / 100_000 * 100)

    await service.overview()
    assert source.calls == 1  # cached
    service.invalidate()
    clock.now = datetime(2026, 11, 11, 9, 0, tzinfo=PSE_TIME)
    later = await service.overview()
    assert source.calls == 2
    assert not later.is_today and later.session_label == "the last session (Tue 10 Nov)"


async def test_spoken_descriptions() -> None:
    service = PortfolioService(FakePortfolio(snapshot()), clock=FixedClock(TUESDAY))
    text = describe_portfolio(await service.overview())
    assert "worth 101,500 pesos, up 1.5% (1,500 pesos) on the day" in text
    assert "up 6.8% (6,500 pesos) overall" in text
    assert "JFC +2.0% (1,200 pesos); SM -0.5% (203 pesos)" in text

    ideas = describe_ideas(await service.overview())
    assert ideas.startswith("Ideas to research, not financial advice.")
    assert "1. BBB (BBB Corp): Uptrend" in ideas and "3. CCC" in ideas

    empty = PortfolioService(FakePortfolio(snapshot([])), clock=FixedClock(TUESDAY))
    assert "no open positions" in describe_portfolio(await empty.overview())


async def test_no_ideas_explains_the_screen() -> None:
    strict = PortfolioService(FakePortfolio(snapshot()), rules=IdeaRules(min_score=95))
    text = describe_ideas(await strict.overview())
    assert "No PSE stock passes" in text
    assert "RSI 55 or below and a score of +95 or more" in text


# --------------------------------------------------------------- tools etc.


def registry_for(service: PortfolioService) -> ToolRegistry:
    registry = ToolRegistry()
    registry.extend(builtin.portfolio_tools(service))
    return registry


async def test_portfolio_tools() -> None:
    service = PortfolioService(FakePortfolio(snapshot([])), clock=FixedClock(TUESDAY))
    registry = registry_for(service)
    result = await registry.execute(ToolCall("get_portfolio", {}))
    assert "no open positions" in result and "1. BBB" in result  # ideas when holding nothing
    assert "1. BBB" in await registry.execute(ToolCall("get_stock_ideas", {}))

    offline = registry_for(PortfolioService(FakePortfolio(None)))
    assert (await offline.execute(ToolCall("get_portfolio", {}))).startswith(
        "Error: PisoTiyempo isn't reachable"
    )


@pytest.mark.parametrize(
    "request_text",
    [
        "How are my stocks doing?",
        "what should I invest in",
        "How did my portfolio do today",
        "any good PSE picks",
        "check PisoTiyempo",
    ],
)
def test_stock_requests_route_to_the_stock_tools(request_text: str) -> None:
    stocks = next(g for g in BUILTIN_GROUPS if g.name == "stocks")
    assert stocks.matches(request_text)


async def briefing_facts(source: FakePortfolio) -> str:
    db = Database(":memory:")
    briefing = BriefingService(
        tasks=SqliteTaskRepository(db),
        reminders=SqliteReminderRepository(db),
        portfolio=PortfolioService(source, clock=FixedClock(TUESDAY)),
        clock=FixedClock(TUESDAY),
    )
    return await briefing.facts()


async def test_briefing_mentions_the_portfolio_only_with_holdings() -> None:
    assert "PSE portfolio at the close of today" in await briefing_facts(FakePortfolio(snapshot()))
    assert "portfolio" not in (await briefing_facts(FakePortfolio(snapshot([])))).lower()
    # A failing source is skipped, not fatal.
    assert "portfolio" not in (await briefing_facts(FakePortfolio(None))).lower()


def test_doctor_finds_the_export_files(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, portfolio_feed_url="", portfolio_export_dir=str(tmp_path))
    assert check_pisotiyempo(settings).status is Status.WARN
    write_export(tmp_path)
    check = check_pisotiyempo(settings)
    assert check.status is Status.OK and "export files" in check.detail


# --------------------------------------------------------------------- API


def make_container(source: FakePortfolio | None) -> Container:
    return assemble(
        Settings(_env_file=None),
        llm=FakeLlm(["ok"]),
        database=Database(":memory:"),
        vad_factory=FakeVad,
        portfolio=source,
    )


@pytest.fixture
def portfolio_source() -> FakePortfolio:
    return FakePortfolio(snapshot())


@pytest.fixture
def client(portfolio_source: FakePortfolio) -> Iterator[TestClient]:
    with TestClient(create_app(container=make_container(portfolio_source))) as test_client:
        yield test_client


def test_api_returns_holdings_and_ideas(client: TestClient) -> None:
    body = client.get("/api/apps/pisotiyempo").json()
    assert body["status"] == "ok" and body["source"] == "feed"
    assert body["session_date"] == "2026-11-10"
    assert body["totals"]["day_change"] == 1_500.0
    assert [h["symbol"] for h in body["holdings"]] == ["JFC", "SM"]
    assert [i["symbol"] for i in body["ideas"]] == ["BBB", "AAA", "CCC"]
    assert body["disclaimer"] == "Ideas to research, not financial advice."


def test_api_reports_an_unreachable_app_and_a_disabled_integration() -> None:
    with TestClient(create_app(container=make_container(FakePortfolio(None)))) as offline:
        body = offline.get("/api/apps/pisotiyempo").json()
        assert body["status"] == "unavailable" and "PisoTiyempo" in body["message"]
    with TestClient(create_app(container=make_container(None))) as disabled:
        assert disabled.get("/api/apps/pisotiyempo").json()["status"] == "disabled"


def test_feed_address_is_a_live_setting(
    client: TestClient, portfolio_source: FakePortfolio
) -> None:
    assert portfolio_source.feed_url == "http://127.0.0.1:8766"
    response = client.put("/api/settings", json={"portfolio_feed_url": "http://127.0.0.1:9000/"})
    assert response.status_code == 200
    assert portfolio_source.feed_url == "http://127.0.0.1:9000"
    bad = client.put("/api/settings", json={"portfolio_feed_url": "ftp://nope"})
    assert bad.status_code == 400 and "portfolio_feed_url" in bad.json()["detail"]
