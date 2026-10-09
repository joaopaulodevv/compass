"""Inputs and results of the financial engine.

The engine is pure: it takes `Movement` values and returns these result types. It never
touches a database, an HTTP request or a provider, which is what lets every number be
unit-tested against hand-written fixtures (ADR-0005, ADR-0008).

`Movement` is deliberately not the ORM `Transaction`. Keeping a separate, minimal input
type means a calculation cannot accidentally depend on persistence, lazy loading or the
shape of a provider payload.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from compass_api.domain.categories import ExpenseCategory, is_internal
from compass_api.domain.open_finance import AccountType


@dataclass(frozen=True, slots=True)
class Movement:
    """One movement, as the engine sees it. `amount` is signed: negative is an outflow."""

    id: uuid.UUID
    account_id: uuid.UUID
    account_type: AccountType
    booked_at: date
    amount: Decimal
    category: ExpenseCategory
    description: str
    merchant_name: str | None = None

    @property
    def is_internal(self) -> bool:
        return is_internal(self.category)

    @property
    def is_income(self) -> bool:
        """Money arriving from outside.

        Decided by sign, not by category: an unexpected credit - a refund, a reversal -
        is still money arriving, and a category whitelist would drop it from the totals
        instead of counting it.
        """
        return not self.is_internal and self.amount > 0

    @property
    def is_expense(self) -> bool:
        """Money leaving to the outside world."""
        return not self.is_internal and self.amount < 0


@dataclass(frozen=True, slots=True)
class MonthlyCashflow:
    """One calendar month. `expenses` is a positive magnitude."""

    month: date
    income: Decimal
    expenses: Decimal
    net: Decimal
    #: False when the window covers only part of this month, which would otherwise make
    #: the month look artificially cheap.
    is_complete: bool


@dataclass(frozen=True, slots=True)
class CategoryTotal:
    """Spend in one category over the window."""

    category: ExpenseCategory
    total: Decimal
    #: Fraction of total expenses, 0-1, rounded to four places.
    share: Decimal


@dataclass(frozen=True, slots=True)
class CashflowSummary:
    """Income, expenses and the monthly series over a window."""

    since: date
    until: date
    income: Decimal
    expenses: Decimal
    net: Decimal
    #: Magnitude of the internal movements that were deliberately left out, reported so
    #: the exclusion is visible rather than silent.
    internal_movements: Decimal
    months: tuple[MonthlyCashflow, ...]
    by_category: tuple[CategoryTotal, ...]
    movements_considered: int
    movements_excluded: int

    @property
    def complete_months(self) -> tuple[MonthlyCashflow, ...]:
        return tuple(month for month in self.months if month.is_complete)


@dataclass(frozen=True, slots=True)
class RecurringExpense:
    """A charge that repeats on a roughly monthly cadence."""

    signature: str
    label: str
    category: ExpenseCategory
    account_id: uuid.UUID
    occurrences: int
    #: Positive magnitude. Median, not mean: one unusual month must not move it.
    median_amount: Decimal
    average_interval_days: int
    first_seen: date
    last_seen: date
    expected_next: date


@dataclass(frozen=True, slots=True)
class SavingCapacity:
    """How much the user could put aside each month, based on what actually happened."""

    #: The headline figure: the median monthly net, floored at zero.
    sustainable_monthly: Decimal
    monthly_median: Decimal
    monthly_mean: Decimal
    monthly_minimum: Decimal
    monthly_maximum: Decimal
    #: Only whole calendar months inside the window are used.
    months_considered: int
    months: tuple[date, ...]
