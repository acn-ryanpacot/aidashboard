"""Read the PisoTiyempo desktop app's personal dashboard feed.

PisoTiyempo (a PSE investing app) publishes the user's data two ways:

* a read-only JSON API on the loopback interface (``/api/summary``,
  ``/api/holdings``, ``/api/analyses``) while its desktop app is running;
* ``summary.json`` plus CSV files in its export folder, rewritten after every
  sync, so the data is still available when the app is closed.

:class:`PisoTiyempoPortfolio` tries the live feed first and falls back to the
export files. It only ever reads the real-money account (never practice trades).

:class:`PisoTiyempoAlerts` reads the user's alert rules from the app's SQLite
database, which its README offers for exactly this ("open it read-only"). The
feed doesn't expose alerts. The file is opened in read-only mode, so Jarvis can
never change it.

The feed's default port (8765) is the same as the Jarvis core's, so the guide
asks the user to move PisoTiyempo's feed to 8766 (``feedPort=8766`` in its
``config.properties``); that's this adapter's default address too.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import json
import os
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import structlog

from jarvis_core.domain.errors import DataSourceUnavailableError
from jarvis_core.domain.records import (
    AlertBook,
    PortfolioSnapshot,
    PortfolioSummary,
    StockAlertRule,
    StockAnalysis,
    StockHolding,
    StockQuote,
)

log = structlog.get_logger(__name__)

DEFAULT_FEED_URL = "http://127.0.0.1:8766"


def _app_home() -> Path:
    app_data = os.environ.get("APPDATA")
    if os.name == "nt" and app_data:
        return Path(app_data) / "PisoTiyempo"
    return Path.home() / ".pisotiyempo"


def default_export_dir() -> Path:
    r"""Where PisoTiyempo writes its exports by default.

    ``%APPDATA%\PisoTiyempo\export`` on Windows, ``~/.pisotiyempo/export``
    elsewhere (the same rule as the desktop app's ``DesktopPaths``).
    """
    return _app_home() / "export"


def default_database_path() -> Path:
    r"""PisoTiyempo's desktop database: ``%APPDATA%\PisoTiyempo\piso-tiyempo.db``."""
    return _app_home() / "piso-tiyempo.db"


# ------------------------------------------------------------------ parsing
#
# The JSON API and the CSV export use the same camelCase field names. CSV
# values are all strings ("" for missing), so every reader tolerates both.


def _float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _num(value: Any) -> float:
    number = _float(value, 0.0)
    return number if number is not None else 0.0


def _int(value: Any) -> int:
    return round(_num(value))


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return None


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_summary(row: Mapping[str, Any]) -> PortfolioSummary:
    """Build the portfolio totals from ``/api/summary`` or ``summary.json``."""
    return PortfolioSummary(
        as_of=_date(row.get("asOf")),
        market_value=_num(row.get("marketValue")),
        cost_basis=_num(row.get("costBasis")),
        unrealized_pnl=_num(row.get("unrealizedPnl")),
        unrealized_pct=_num(row.get("unrealizedPct")),
        day_change=_num(row.get("dayChange")),
        holdings=_int(row.get("holdings")),
    )


def parse_holding(row: Mapping[str, Any]) -> StockHolding:
    """One row of ``/api/holdings`` or ``holdings.csv``."""
    return StockHolding(
        symbol=str(row.get("symbol", "")).strip().upper(),
        sector=str(row.get("sector") or ""),
        shares=_int(row.get("shares")),
        avg_cost=_num(row.get("avgCost")),
        last_price=_float(row.get("lastPrice")),
        change_pct=_float(row.get("changePct")),
        market_value=_num(row.get("marketValue")),
        unrealized_pnl=_num(row.get("unrealizedPnl")),
        unrealized_pct=_num(row.get("unrealizedPct")),
    )


def parse_analysis(row: Mapping[str, Any]) -> StockAnalysis:
    """One row of ``/api/analyses`` or ``analyses.csv``."""
    return StockAnalysis(
        symbol=str(row.get("symbol", "")).strip().upper(),
        name=str(row.get("name") or ""),
        sector=str(row.get("sector") or ""),
        close=_num(row.get("close")),
        change_pct=_float(row.get("changePct")),
        score=_int(row.get("score")),
        stance=str(row.get("stance") or ""),
        rsi14=_float(row.get("rsi14")),
        above_sma50=_bool(row.get("aboveSma50")),
        above_sma200=_bool(row.get("aboveSma200")),
        return_3m_pct=_float(row.get("return3mPct")),
        is_liquid=_bool(row.get("isLiquid")) is True,
    )


def build_snapshot(
    summary: Mapping[str, Any],
    holdings: Sequence[Mapping[str, Any]],
    analyses: Sequence[Mapping[str, Any]],
    source: str,
) -> PortfolioSnapshot:
    """Assemble a snapshot from raw rows (positions with no shares are dropped)."""
    return PortfolioSnapshot(
        summary=parse_summary(summary),
        holdings=tuple(h for h in map(parse_holding, holdings) if h.symbol and h.shares > 0),
        analyses=tuple(a for a in map(parse_analysis, analyses) if a.symbol),
        source=source,
    )


# ------------------------------------------------------------------ adapter


class PisoTiyempoPortfolio:
    """Implements :class:`~jarvis_core.domain.ports.PortfolioSource`.

    Args:
        feed_url: Base address of the desktop app's feed ("" = files only).
        export_dir: The app's export folder (``None`` = its default location).
        client: Inject a custom :class:`httpx.AsyncClient` (used by tests).
    """

    def __init__(
        self,
        feed_url: str = DEFAULT_FEED_URL,
        export_dir: Path | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._feed_url = feed_url.rstrip("/")
        self._export_dir = export_dir or default_export_dir()
        # The feed is on this machine: answer fast or fall back to the files.
        self._client = client or httpx.AsyncClient(timeout=3.0)

    def set_feed_url(self, url: str) -> None:
        """Read from ``url`` from now on (live Settings)."""
        self._feed_url = url.strip().rstrip("/")

    async def snapshot(self) -> PortfolioSnapshot:
        """Read the live feed, or the export files if the app isn't running."""
        feed_error = ""
        if self._feed_url:
            try:
                return await self._from_feed()
            except (httpx.HTTPError, ValueError) as exc:
                feed_error = str(exc) or type(exc).__name__
                log.info("pisotiyempo_feed_unavailable", url=self._feed_url, error=feed_error)
        snapshot = await asyncio.to_thread(self._from_files)
        if snapshot is not None:
            return snapshot
        where = f"at {self._feed_url} " if self._feed_url else ""
        raise DataSourceUnavailableError(
            f"PisoTiyempo isn't reachable {where}and no export was found in {self._export_dir}. "
            "Open the PisoTiyempo desktop app and let it sync."
        )

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    async def _get(self, path: str) -> Any:
        response = await self._client.get(f"{self._feed_url}{path}")
        response.raise_for_status()
        return response.json()

    async def _from_feed(self) -> PortfolioSnapshot:
        summary, holdings, analyses = await asyncio.gather(
            self._get("/api/summary"),
            self._get("/api/holdings?account=REAL"),
            self._get("/api/analyses"),
        )
        if not isinstance(summary, dict) or not isinstance(holdings, list):
            raise ValueError("unexpected response shape from the PisoTiyempo feed")
        return build_snapshot(
            summary, holdings, analyses if isinstance(analyses, list) else [], "feed"
        )

    def _from_files(self) -> PortfolioSnapshot | None:
        folder = self._export_dir
        summary_file = folder / "summary.json"
        if not summary_file.is_file():
            return None
        try:
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            holdings = _read_csv(folder / "holdings.csv")
            analyses = _read_csv(folder / "analyses.csv")
        except (OSError, ValueError) as exc:
            log.warning("pisotiyempo_export_unreadable", folder=str(folder), error=str(exc))
            return None
        return build_snapshot(summary, holdings, analyses, "files")


class PisoTiyempoAlerts:
    """Implements :class:`~jarvis_core.domain.ports.StockAlertSource`.

    Reads the ``alerts``, ``stocks`` and ``analyses`` tables of PisoTiyempo's
    desktop database (synced from the phone), always read-only.

    Args:
        database: Path to ``piso-tiyempo.db`` (``None`` = its default location).
    """

    def __init__(self, database: Path | None = None) -> None:
        self._database = database or default_database_path()

    async def alert_book(self) -> AlertBook:
        """Active alerts and the latest quotes for their symbols."""
        return await asyncio.to_thread(self._read)

    def _read(self) -> AlertBook:
        if not self._database.is_file():
            raise DataSourceUnavailableError(f"PisoTiyempo's database isn't at {self._database}")
        uri = f"{self._database.resolve().as_uri()}?mode=ro"
        try:
            with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=2)) as conn:
                conn.row_factory = sqlite3.Row
                return read_alert_book(conn)
        except sqlite3.Error as exc:
            raise DataSourceUnavailableError(f"couldn't read PisoTiyempo's alerts: {exc}") from exc


def read_alert_book(conn: sqlite3.Connection) -> AlertBook:
    """Read alert rules and quotes from a PisoTiyempo database connection.

    A database without an ``alerts`` table (older app versions) has no alerts.
    """
    try:
        rows = conn.execute(
            "SELECT uid, symbol, kind, threshold FROM alerts WHERE active = 1 ORDER BY createdAt"
        ).fetchall()
    except sqlite3.OperationalError:
        return AlertBook((), {})
    rules = tuple(
        StockAlertRule(
            uid=str(r["uid"]),
            symbol=str(r["symbol"]).upper(),
            kind=str(r["kind"]),
            threshold=_float(r["threshold"]),
        )
        for r in rows
    )
    symbols = sorted({rule.symbol for rule in rules})
    if not symbols:
        return AlertBook(rules, {})
    marks = ",".join("?" * len(symbols))
    quotes: dict[str, StockQuote] = {}
    query = (
        # Only "?" placeholders are interpolated; the symbols are bound parameters.
        "SELECT s.symbol, s.close, s.date, a.score, a.asOf, a.patternNames FROM stocks s "
        f"LEFT JOIN analyses a ON a.symbol = s.symbol WHERE s.symbol IN ({marks})"
    )
    for r in conn.execute(query, symbols):
        day = _date(r["date"])
        if day is None:
            continue
        patterns = tuple(p.strip() for p in str(r["patternNames"] or "").splitlines() if p.strip())
        quotes[str(r["symbol"]).upper()] = StockQuote(
            symbol=str(r["symbol"]).upper(),
            close=_num(r["close"]),
            day=day,
            score=None if r["score"] is None else int(r["score"]),
            analysis_date=_date(r["asOf"]),
            patterns=patterns,
        )
    return AlertBook(rules, quotes)


def _read_csv(path: Path) -> list[Mapping[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
