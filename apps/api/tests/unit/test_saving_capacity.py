"""Sustainable saving capacity."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from compass_api.domain.analysis import CashflowSummary, MonthlyCashflow
from compass_api.services.saving_capacity import estimate

ZERO = Decimal("0.00")


def month(value: str, when: date, *, complete: bool = True) -> MonthlyCashflow:
    net = Decimal(value)
    return MonthlyCashflow(
        month=when,
        income=max(net, ZERO),
        expenses=max(-net, ZERO),
        net=net,
        is_complete=complete,
    )


def summary(*months: MonthlyCashflow) -> CashflowSummary:
    return CashflowSummary(
        since=date(2026, 1, 1),
        until=date(2026, 6, 30),
        income=ZERO,
        expenses=ZERO,
        net=ZERO,
        internal_movements=ZERO,
        months=months,
        by_category=(),
        movements_considered=0,
        movements_excluded=0,
    )


def test_capacity_is_the_median_monthly_net() -> None:
    capacity = estimate(
        summary(
            month("1000.00", date(2026, 1, 1)),
            month("1500.00", date(2026, 2, 1)),
            month("2000.00", date(2026, 3, 1)),
        )
    )

    assert capacity.sustainable_monthly == Decimal("1500.00")
    assert capacity.monthly_median == Decimal("1500.00")
    assert capacity.months_considered == 3


def test_an_even_number_of_months_averages_the_middle_two() -> None:
    capacity = estimate(
        summary(
            month("1000.00", date(2026, 1, 1)),
            month("1500.00", date(2026, 2, 1)),
            month("1800.00", date(2026, 3, 1)),
            month("2000.00", date(2026, 4, 1)),
        )
    )

    assert capacity.monthly_median == Decimal("1650.00")


def test_a_bonus_month_does_not_inflate_what_the_user_is_told() -> None:
    """Why the median and not the mean: one windfall must not become a monthly promise."""
    months = (
        month("1000.00", date(2026, 1, 1)),
        month("1100.00", date(2026, 2, 1)),
        month("1050.00", date(2026, 3, 1)),
        month("1200.00", date(2026, 4, 1)),
        month("9000.00", date(2026, 5, 1)),
    )

    capacity = estimate(summary(*months))

    assert capacity.monthly_median == Decimal("1100.00")
    assert capacity.monthly_mean == Decimal("2670.00")
    assert capacity.sustainable_monthly == capacity.monthly_median


def test_partial_months_are_left_out() -> None:
    """A half month looks cheap and would overstate what can be saved."""
    capacity = estimate(
        summary(
            month("300.00", date(2026, 1, 1), complete=False),
            month("1000.00", date(2026, 2, 1)),
            month("1200.00", date(2026, 3, 1)),
            month("200.00", date(2026, 4, 1), complete=False),
        )
    )

    assert capacity.months_considered == 2
    assert capacity.months == (date(2026, 2, 1), date(2026, 3, 1))
    assert capacity.monthly_median == Decimal("1100.00")


def test_spending_more_than_earned_means_no_capacity_not_a_negative_one() -> None:
    capacity = estimate(
        summary(
            month("-500.00", date(2026, 1, 1)),
            month("-200.00", date(2026, 2, 1)),
            month("-800.00", date(2026, 3, 1)),
        )
    )

    assert capacity.sustainable_monthly == ZERO
    assert capacity.monthly_median == Decimal("-500.00")
    assert capacity.monthly_minimum == Decimal("-800.00")
    assert capacity.monthly_maximum == Decimal("-200.00")


def test_no_complete_month_means_not_enough_history() -> None:
    """Reported as zero months considered, so a caller can say so rather than guess."""
    capacity = estimate(summary(month("1000.00", date(2026, 1, 1), complete=False)))

    assert capacity.months_considered == 0
    assert capacity.sustainable_monthly == ZERO
    assert capacity.months == ()
