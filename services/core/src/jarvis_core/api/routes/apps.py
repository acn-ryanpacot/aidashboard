"""Data from companion apps, proxied for their dashboard widgets.

Each app gets one route under ``/api/apps/<app>``; the widget's manifest
names it as its ``source.endpoint`` (see ``packages/widget-sdk``).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis_core.application.portfolio import DISCLAIMER
from jarvis_core.container import Container
from jarvis_core.domain.errors import DataSourceUnavailableError

router = APIRouter(prefix="/api/apps", tags=["apps"])


class PortfolioTotalsOut(BaseModel):
    """Portfolio totals (pesos; percentages in percent)."""

    market_value: float
    cost_basis: float
    day_change: float
    day_change_pct: float | None
    unrealized_pnl: float
    unrealized_pct: float


class HoldingOut(BaseModel):
    """One position and its move on the day."""

    symbol: str
    sector: str
    shares: int
    last_price: float | None
    change_pct: float | None
    day_change: float
    market_value: float
    unrealized_pnl: float
    unrealized_pct: float


class IdeaOut(BaseModel):
    """A stock that passed the trend-and-value screen."""

    symbol: str
    name: str
    sector: str
    close: float
    change_pct: float | None
    score: int
    rsi14: float | None
    return_3m_pct: float | None
    reasons: list[str]


class PisoTiyempoOut(BaseModel):
    """What the Portfolio widget shows.

    ``status`` is ``disabled`` when the integration is off, ``unavailable``
    when PisoTiyempo can't be reached (``message`` says why), else ``ok``.
    """

    status: Literal["ok", "unavailable", "disabled"]
    message: str = ""
    source: str = ""
    session_date: date | None = None
    is_today: bool = False
    totals: PortfolioTotalsOut | None = None
    holdings: list[HoldingOut] = []
    ideas: list[IdeaOut] = []
    screen: str = ""
    disclaimer: str = DISCLAIMER


@router.get("/pisotiyempo", response_model=PisoTiyempoOut)
async def get_pisotiyempo(request: Request) -> PisoTiyempoOut:
    """Your PSE portfolio from PisoTiyempo, plus trend-and-value ideas."""
    container: Container = request.app.state.container
    service = container.portfolio
    if service is None:
        return PisoTiyempoOut(status="disabled", message="The portfolio integration is off.")
    try:
        overview = await service.overview()
    except DataSourceUnavailableError as exc:
        return PisoTiyempoOut(status="unavailable", message=str(exc))
    s = overview.summary
    return PisoTiyempoOut(
        status="ok",
        source=overview.source,
        session_date=overview.session_date,
        is_today=overview.is_today,
        totals=PortfolioTotalsOut(
            market_value=s.market_value,
            cost_basis=s.cost_basis,
            day_change=s.day_change,
            day_change_pct=overview.day_change_pct,
            unrealized_pnl=s.unrealized_pnl,
            unrealized_pct=s.unrealized_pct,
        ),
        holdings=[
            HoldingOut(
                symbol=m.holding.symbol,
                sector=m.holding.sector,
                shares=m.holding.shares,
                last_price=m.holding.last_price,
                change_pct=m.holding.change_pct,
                day_change=m.day_change,
                market_value=m.holding.market_value,
                unrealized_pnl=m.holding.unrealized_pnl,
                unrealized_pct=m.holding.unrealized_pct,
            )
            for m in overview.holdings
        ],
        ideas=[
            IdeaOut(
                symbol=i.analysis.symbol,
                name=i.analysis.name,
                sector=i.analysis.sector,
                close=i.analysis.close,
                change_pct=i.analysis.change_pct,
                score=i.analysis.score,
                rsi14=i.analysis.rsi14,
                return_3m_pct=i.analysis.return_3m_pct,
                reasons=list(i.reasons),
            )
            for i in overview.ideas
        ],
        screen=overview.rules.describe(),
    )
