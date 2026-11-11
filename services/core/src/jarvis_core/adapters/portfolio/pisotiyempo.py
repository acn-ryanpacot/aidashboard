"""Read the PisoTiyempo desktop app's personal dashboard feed.

PisoTiyempo (a PSE investing app) publishes the user's data two ways:

* a read-only JSON API on the loopback interface (``/api/summary``,
  ``/api/holdings``, ``/api/analyses``) while its desktop app is running;
* ``summary.json`` plus CSV files in its export folder, rewritten after every
  sync, so the data is still available when the app is closed.

This adapter tries the live feed first and falls back to the export files.
It only ever reads the real-money account (never practice trades).

The feed's default port (8765) is the same as the Jarvis core's, so the guide
asks the user to move PisoTiyempo's feed to 8766 (``feedPort=8766`` in its
``config.properties``); that's this adapter's default address too.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import structlog

from jarvis_core.domain.errors import DataSourceUnavailableError
from jarvis_core.domain.records import (
    PortfolioSnapshot,
    PortfolioSummary,
    StockAnalysis,
    StockHolding,
)

log = structlog.get_logger(__name__)

DEFAULT_FEED_URL = "http://127.0.0.1:8766"


def default_export_dir() -> Path:
    r"""Where PisoTiyempo writes its exports by default.

    ``%APPDATA%\PisoTiyempo\export`` on Windows, ``~/.pisotiyempo/export``
    elsewhere (the same rule as the desktop app's ``DesktopPaths``).
    """
    app_data = os.environ.get("APPDATA")
    if os.name == "nt" and app_data:
        return Path(app_data) / "PisoTiyempo" / "export"
    return Path.home() / ".pisotiyempo" / "export"


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


def _read_csv(path: Path) -> list[Mapping[str, Any]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
