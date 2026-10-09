"""Cash flow over a window.

Pure: it takes movements and returns numbers. No database, no HTTP, no provider - which
is what makes every figure reproducible and unit-testable (ADR-0008).

The one rule that makes the output correct rather than merely plausible: **internal
movements are excluded**. Paying the credit-card bill is not spending, because the
spending already happened when the card was used; moving money to one's own savings is
not spending either. Counting them would inflate expenses by exactly the amount that was
already counted elsewhere. They are still reported, as a separate total, so the
exclusion is visible rather than silent.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from compass_api.domain.analysis import (
    CashflowSummary,
    CategoryTotal,
    MonthlyCashflow,
    Movement,
)
from compass_api.domain.categories import ExpenseCategory

SHARE_PRECISION = Decimal("0.0001")

ZERO = Decimal("0.00")


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _month_end(day: date) -> date:
    return day.replace(day=calendar.monthrange(day.year, day.month)[1])


def summarize(movements: Iterable[Movement], since: date, until: date) -> CashflowSummary:
    """Aggregate movements booked in the inclusive window `[since, until]`.

    Movements outside the window are ignored, so a caller may pass more than it asks
    about. Months with no movements do not appear: an absent month is unknown, not zero,
    and zero-filling would drag down any median taken over the series.

    Raises:
        ValueError: if the window is inverted.
    """
    if since > until:
        raise ValueError("since must not be later than until")

    in_window = [movement for movement in movements if since <= movement.booked_at <= until]

    income = ZERO
    expenses = ZERO
    internal = ZERO
    excluded = 0
    per_month: dict[date, list[Movement]] = defaultdict(list)
    per_category: dict[ExpenseCategory, Decimal] = defaultdict(lambda: ZERO)

    for movement in in_window:
        if movement.is_internal:
            internal += abs(movement.amount)
            excluded += 1
            continue

        per_month[_month_start(movement.booked_at)].append(movement)
        if movement.is_income:
            income += movement.amount
        elif movement.is_expense:
            expenses += -movement.amount
            per_category[movement.category] += -movement.amount

    return CashflowSummary(
        since=since,
        until=until,
        income=income,
        expenses=expenses,
        net=income - expenses,
        internal_movements=internal,
        months=_monthly_series(per_month, since, until),
        by_category=_category_totals(per_category, expenses),
        movements_considered=len(in_window) - excluded,
        movements_excluded=excluded,
    )


def _monthly_series(
    per_month: dict[date, list[Movement]], since: date, until: date
) -> tuple[MonthlyCashflow, ...]:
    months = []
    for month in sorted(per_month):
        income = sum(
            (movement.amount for movement in per_month[month] if movement.is_income),
            start=ZERO,
        )
        expenses = sum(
            (-movement.amount for movement in per_month[month] if movement.is_expense),
            start=ZERO,
        )
        months.append(
            MonthlyCashflow(
                month=month,
                income=income,
                expenses=expenses,
                net=income - expenses,
                # A partial month would look artificially cheap, so it is marked and the
                # saving-capacity estimate leaves it out.
                is_complete=month >= since and _month_end(month) <= until,
            )
        )
    return tuple(months)


def _category_totals(
    per_category: dict[ExpenseCategory, Decimal], expenses: Decimal
) -> tuple[CategoryTotal, ...]:
    def share(total: Decimal) -> Decimal:
        if expenses <= 0:
            return Decimal("0.0000")
        return (total / expenses).quantize(SHARE_PRECISION, rounding=ROUND_HALF_UP)

    ordered: Sequence[tuple[ExpenseCategory, Decimal]] = sorted(
        per_category.items(), key=lambda item: (-item[1], item[0].value)
    )
    return tuple(
        CategoryTotal(category=category, total=total, share=share(total))
        for category, total in ordered
    )
