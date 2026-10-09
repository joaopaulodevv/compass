"""Computed views over the user's financial history.

Nothing here is stored: every figure is derived on request by the deterministic engine,
from transactions the user owns. That is why the endpoints live under `/insights` rather
than looking like resources.

Amounts are JSON strings for the same reason as everywhere else: they are decimals, and a
JSON number would hand clients a float to round badly.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from compass_api.api.deps import CurrentUserId, SessionDep
from compass_api.domain.analysis import (
    CashflowSummary,
    CategoryTotal,
    MonthlyCashflow,
    RecurringExpense,
    SavingCapacity,
)
from compass_api.domain.categories import ExpenseCategory
from compass_api.services.insights import AnalysisWindow, InsightsService

router = APIRouter(prefix="/insights", tags=["insights"])

SinceQuery = Annotated[date | None, Query(description="Start of the window, inclusive")]
UntilQuery = Annotated[date | None, Query(description="End of the window, inclusive")]


def _window(since: date | None, until: date | None) -> AnalysisWindow:
    try:
        return AnalysisWindow.resolve(since, until)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
        ) from error


class MonthlyCashflowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: date
    income: Decimal
    expenses: Decimal
    net: Decimal
    is_complete: bool


class CategoryTotalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: ExpenseCategory
    total: Decimal
    share: Decimal


class CashflowResponse(BaseModel):
    """Income, expenses and the monthly series over the window.

    `expenses` is a positive magnitude. `internal_movements` is the total that was
    deliberately left out - credit-card bill payments and transfers between the user's own
    accounts - reported so the exclusion is visible rather than silent.
    """

    since: date
    until: date
    income: Decimal
    expenses: Decimal
    net: Decimal
    internal_movements: Decimal
    movements_considered: int
    movements_excluded: int
    months: list[MonthlyCashflowResponse]
    by_category: list[CategoryTotalResponse]

    @classmethod
    def of(cls, summary: CashflowSummary) -> CashflowResponse:
        return cls(
            since=summary.since,
            until=summary.until,
            income=summary.income,
            expenses=summary.expenses,
            net=summary.net,
            internal_movements=summary.internal_movements,
            movements_considered=summary.movements_considered,
            movements_excluded=summary.movements_excluded,
            months=[_month(month) for month in summary.months],
            by_category=[_category(total) for total in summary.by_category],
        )


def _month(month: MonthlyCashflow) -> MonthlyCashflowResponse:
    return MonthlyCashflowResponse.model_validate(month)


def _category(total: CategoryTotal) -> CategoryTotalResponse:
    return CategoryTotalResponse.model_validate(total)


class RecurringExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signature: str
    label: str
    category: ExpenseCategory
    account_id: UUID
    occurrences: int
    median_amount: Decimal
    average_interval_days: int
    first_seen: date
    last_seen: date
    expected_next: date


class RecurringExpenseListResponse(BaseModel):
    since: date
    until: date
    items: list[RecurringExpenseResponse]
    monthly_total: Decimal = Field(
        description="Sum of the median amounts: the monthly commitment these represent."
    )

    @classmethod
    def of(
        cls, window: AnalysisWindow, expenses: tuple[RecurringExpense, ...]
    ) -> RecurringExpenseListResponse:
        return cls(
            since=window.since,
            until=window.until,
            items=[RecurringExpenseResponse.model_validate(item) for item in expenses],
            monthly_total=sum((item.median_amount for item in expenses), start=Decimal("0.00")),
        )


class SavingCapacityResponse(BaseModel):
    """What the user could put aside monthly, from what actually happened.

    `sustainable_monthly` is the median monthly net, floored at zero, over whole calendar
    months only. `months_considered == 0` means there is not enough history to answer -
    not that the capacity is zero.
    """

    since: date
    until: date
    sustainable_monthly: Decimal
    monthly_median: Decimal
    monthly_mean: Decimal
    monthly_minimum: Decimal
    monthly_maximum: Decimal
    months_considered: int
    months: list[date]

    @classmethod
    def of(cls, window: AnalysisWindow, capacity: SavingCapacity) -> SavingCapacityResponse:
        return cls(
            since=window.since,
            until=window.until,
            sustainable_monthly=capacity.sustainable_monthly,
            monthly_median=capacity.monthly_median,
            monthly_mean=capacity.monthly_mean,
            monthly_minimum=capacity.monthly_minimum,
            monthly_maximum=capacity.monthly_maximum,
            months_considered=capacity.months_considered,
            months=list(capacity.months),
        )


@router.get("/cashflow", summary="Income, expenses and the monthly series")
async def get_cashflow(
    user_id: CurrentUserId,
    session: SessionDep,
    since: SinceQuery = None,
    until: UntilQuery = None,
) -> CashflowResponse:
    window = _window(since, until)
    return CashflowResponse.of(await InsightsService(session).cashflow(user_id, window))


@router.get("/recurring-expenses", summary="Charges that repeat every month")
async def get_recurring_expenses(
    user_id: CurrentUserId,
    session: SessionDep,
    since: SinceQuery = None,
    until: UntilQuery = None,
) -> RecurringExpenseListResponse:
    window = _window(since, until)
    found = await InsightsService(session).recurring_expenses(user_id, window)
    return RecurringExpenseListResponse.of(window, found)


@router.get("/saving-capacity", summary="Sustainable monthly saving capacity")
async def get_saving_capacity(
    user_id: CurrentUserId,
    session: SessionDep,
    since: SinceQuery = None,
    until: UntilQuery = None,
) -> SavingCapacityResponse:
    window = _window(since, until)
    capacity = await InsightsService(session).saving_capacity(user_id, window)
    return SavingCapacityResponse.of(window, capacity)
