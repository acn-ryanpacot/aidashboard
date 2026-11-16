"""``GET /api/money``: debts and upcoming payments for the Money widget.

The data comes from the user's own spreadsheets in the documents folder
(see :mod:`jarvis_core.application.money`); nothing is fetched from a bank.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from jarvis_core.application.money import Debt, MoneyOverview, Payment
from jarvis_core.container import Container

router = APIRouter(prefix="/api", tags=["money"])


class DebtOut(BaseModel):
    """One debt."""

    name: str
    balance: float
    monthly: float | None
    rate: float | None
    file: str

    @classmethod
    def of(cls, debt: Debt) -> DebtOut:
        """Build from the read model."""
        return cls(
            name=debt.name,
            balance=debt.balance,
            monthly=debt.monthly,
            rate=debt.rate,
            file=debt.file,
        )


class PaymentOut(BaseModel):
    """A bill or debt payment with its due date (``days`` < 0 = overdue)."""

    name: str
    amount: float | None
    due: date
    days: int
    kind: Literal["bill", "debt"]
    recurring: bool
    file: str

    @classmethod
    def of(cls, payment: Payment) -> PaymentOut:
        """Build from the read model."""
        return cls(
            name=payment.name,
            amount=payment.amount,
            due=payment.due,
            days=payment.days,
            kind=payment.kind,
            recurring=payment.recurring,
            file=payment.file,
        )


class MoneyOut(BaseModel):
    """Everything the Money widget shows."""

    status: Literal["ok", "no_folder", "no_sheets", "disabled"]
    today: date
    currency: str
    total_owed: float
    monthly_total: float
    debts: list[DebtOut]
    payments: list[PaymentOut]
    sources: list[str]
    reminder_days: int

    @classmethod
    def of(cls, overview: MoneyOverview, reminder_days: int) -> MoneyOut:
        """Build from the read model."""
        return cls(
            status=overview.status,
            today=overview.today,
            currency=overview.currency,
            total_owed=overview.total_owed,
            monthly_total=overview.monthly_total,
            debts=[DebtOut.of(d) for d in overview.debts],
            payments=[PaymentOut.of(p) for p in overview.payments],
            sources=list(overview.sources),
            reminder_days=reminder_days,
        )


@router.get("/money", response_model=MoneyOut)
async def get_money(request: Request) -> MoneyOut:
    """Debts (largest first) and payments due in the next month (soonest first)."""
    container: Container = request.app.state.container
    days = container.runtime.current.bill_reminder_days
    if container.money is None:
        return MoneyOut.of(MoneyOverview(status="no_folder", today=date.today()), days).model_copy(
            update={"status": "disabled"}
        )
    return MoneyOut.of(await container.money.overview(), days)
