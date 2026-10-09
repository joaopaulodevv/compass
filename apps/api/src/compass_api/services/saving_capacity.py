"""How much the user could put aside each month.

Derived from what actually happened, never from a rule of thumb: the figure is the
median of the monthly net cash flows, which already has rent, bills and subscriptions
subtracted from income.

Two choices make the number trustworthy:

* **Only whole calendar months count.** A partial month looks artificially cheap, and
  including it would quietly overstate capacity.
* **The median, not the mean.** A bonus month or an annual premium should not change what
  the user is told they can save every month.

The result is floored at zero: a negative median means the months were spending more than
they earned, and the honest answer is that there is no capacity to save - not a negative
amount to put aside.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from compass_api.domain.analysis import CashflowSummary, SavingCapacity
from compass_api.domain.money import mean_money, median_money, quantize_money

ZERO = Decimal("0.00")


def estimate(summary: CashflowSummary) -> SavingCapacity:
    """Estimate sustainable monthly saving from a cash-flow summary."""
    months = summary.complete_months
    if not months:
        # No complete month means no evidence. Reporting zero capacity with
        # `months_considered == 0` lets the caller say "not enough history yet" instead
        # of presenting a guess as a measurement.
        return SavingCapacity(
            sustainable_monthly=ZERO,
            monthly_median=ZERO,
            monthly_mean=ZERO,
            monthly_minimum=ZERO,
            monthly_maximum=ZERO,
            months_considered=0,
            months=(),
        )

    nets = [month.net for month in months]
    median = median_money(nets)
    considered: tuple[date, ...] = tuple(month.month for month in months)

    return SavingCapacity(
        sustainable_monthly=max(median, ZERO),
        monthly_median=median,
        monthly_mean=mean_money(nets),
        monthly_minimum=quantize_money(min(nets)),
        monthly_maximum=quantize_money(max(nets)),
        months_considered=len(months),
        months=considered,
    )
