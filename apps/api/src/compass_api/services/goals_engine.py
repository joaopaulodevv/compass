"""The goal engine: pure, deterministic, no I/O.

Answers four questions, and nothing else:

* *How long will this take?* - `simulate`
* *What would it take to hit the date?* - `gap`
* *How do these options compare?* - `compare_paths`
* *Am I ahead or behind?* - `progress`

Projections step one month at a time rather than using a closed-form annuity formula.
That is a deliberate choice: the loop is the definition of what happens - contribute,
then earn a return on the balance - so it can be read, checked by hand against a
spreadsheet, and extended later (a contribution that changes, a withdrawal) without
re-deriving algebra. At a 100-year horizon it is at most 1,200 iterations of decimal
arithmetic.

Returns are expressed as an **effective annual rate** and converted to a monthly rate
properly - `(1 + annual) ** (1/12) - 1`, not `annual / 12`. Dividing by twelve would
overstate monthly growth and quietly flatter every projection.

The engine takes the rate as an argument and never guesses it: Compass does not yet know
what any product pays, and inventing a number here would be exactly the kind of
confident-but-unsourced figure the architecture exists to prevent.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from compass_api.domain.dates import add_months, months_between
from compass_api.domain.goals import (
    GoalGap,
    GoalPath,
    GoalPathOption,
    GoalProgress,
    GoalSimulation,
    GoalTerms,
)
from compass_api.domain.money import ceil_money, quantize_money

ZERO = Decimal("0.00")
ONE = Decimal(1)

#: How far a projection will look ahead before calling a goal unreachable. A hundred
#: years is not a plan; it is a way of saying "never" with a number attached.
MAX_HORIZON_MONTHS = 1200

SHARE_PRECISION = Decimal("0.0001")


def monthly_rate(annual_return_rate: Decimal) -> Decimal:
    """Effective monthly rate equivalent to an effective annual rate."""
    if annual_return_rate == 0:
        return Decimal(0)
    return (ONE + annual_return_rate) ** (ONE / Decimal(12)) - ONE


def simulate(
    terms: GoalTerms,
    monthly_contribution: Decimal,
    annual_return_rate: Decimal = Decimal("0"),
    *,
    as_of: date | None = None,
) -> GoalSimulation:
    """Project the goal forward at a fixed monthly contribution.

    Contributions are made at the end of each month and earn a return from the following
    month, which is the conservative reading of the two.
    """
    start = as_of or date.today()
    rate = monthly_rate(annual_return_rate)

    balance = terms.current_amount
    contributed = ZERO
    months = 0

    if terms.is_reached:
        return GoalSimulation(
            monthly_contribution=quantize_money(monthly_contribution),
            annual_return_rate=annual_return_rate,
            months_to_target=0,
            projected_completion=start,
            projected_amount=quantize_money(balance),
            total_contributed=ZERO,
            total_return=ZERO,
        )

    # The balance keeps full precision while compounding, but reaching the target is
    # judged on the balance rounded to the centavo. Money is only meaningful to the
    # centavo, and without this R$ 10,000 at an effective 10% a year would "fail" to
    # reach R$ 11,000 in twelve months by a fraction of a cent of decimal residue.
    while quantize_money(balance) < terms.target_amount and months < MAX_HORIZON_MONTHS:
        balance = balance * (ONE + rate) + monthly_contribution
        contributed += monthly_contribution
        months += 1

    reached = quantize_money(balance) >= terms.target_amount
    growth = balance - terms.current_amount - contributed

    return GoalSimulation(
        monthly_contribution=quantize_money(monthly_contribution),
        annual_return_rate=annual_return_rate,
        months_to_target=months if reached else None,
        projected_completion=add_months(start, months) if reached else None,
        projected_amount=quantize_money(balance),
        total_contributed=quantize_money(contributed),
        total_return=quantize_money(growth),
    )


def project_balance(
    terms: GoalTerms,
    monthly_contribution: Decimal,
    annual_return_rate: Decimal,
    months: int,
) -> Decimal:
    """Balance after a fixed number of monthly contributions."""
    rate = monthly_rate(annual_return_rate)
    balance = terms.current_amount
    for _ in range(months):
        balance = balance * (ONE + rate) + monthly_contribution
    return quantize_money(balance)


def required_monthly(
    terms: GoalTerms, months: int, annual_return_rate: Decimal = Decimal("0")
) -> Decimal:
    """The contribution that lands exactly on the target in `months` months.

    With no expected return this is simply the remainder divided by the months. With a
    return it is the annuity payment that closes the gap after the existing balance has
    grown - solved from the same month-by-month definition `simulate` uses, so the two
    can never disagree.

    With no months left, the answer is the whole remainder: it would have to be found at
    once.

    Rounded **up** to the centavo: contributing a figure rounded to nearest would land
    short of the target, and a requirement that does not meet the requirement is worse
    than useless.
    """
    if terms.is_reached:
        return ZERO
    if months <= 0:
        return ceil_money(terms.remaining)

    rate = monthly_rate(annual_return_rate)
    if rate == 0:
        return ceil_money(terms.remaining / months)

    # Future value of the current balance, and of one unit contributed every month.
    growth = (ONE + rate) ** months
    annuity_factor = (growth - ONE) / rate
    needed = terms.target_amount - terms.current_amount * growth
    if needed <= 0:
        return ZERO
    return ceil_money(needed / annuity_factor)


def gap(
    terms: GoalTerms,
    planned_monthly: Decimal,
    annual_return_rate: Decimal = Decimal("0"),
    *,
    as_of: date | None = None,
) -> GoalGap:
    """Compare what the date demands against what the user can actually put in.

    Raises:
        ValueError: if the goal has no target date - there is no gap without a deadline.
    """
    if terms.target_date is None:
        raise ValueError("a goal without a target date has no gap to measure")

    start = as_of or date.today()
    months = months_between(start, terms.target_date)
    required = required_monthly(terms, months, annual_return_rate)
    projected = project_balance(terms, planned_monthly, annual_return_rate, months)
    shortfall_total = max(terms.target_amount - projected, ZERO)

    return GoalGap(
        target_date=terms.target_date,
        months_available=months,
        required_monthly=required,
        planned_monthly=quantize_money(planned_monthly),
        projected_amount=projected,
        shortfall_total=quantize_money(shortfall_total),
        shortfall_monthly=quantize_money(max(required - planned_monthly, ZERO)),
        on_track=shortfall_total <= 0,
    )


def compare_paths(
    terms: GoalTerms, options: Sequence[GoalPathOption], *, as_of: date | None = None
) -> tuple[GoalPath, ...]:
    """Simulate several scenarios so they can be put side by side.

    Ordered by how soon the goal is reached, with the unreachable ones last - the
    ordering a reader wants, rather than the order the options arrived in.
    """
    paths = [
        GoalPath(
            label=option.label,
            simulation=simulate(
                terms, option.monthly_contribution, option.annual_return_rate, as_of=as_of
            ),
        )
        for option in options
    ]
    return tuple(
        sorted(
            paths,
            key=lambda path: (
                path.simulation.months_to_target is None,
                path.simulation.months_to_target or 0,
                path.label,
            ),
        )
    )


def progress(terms: GoalTerms, *, as_of: date | None = None) -> GoalProgress:
    """Where the goal stands against the straight line to its target date."""
    today = as_of or date.today()
    share = (
        (terms.current_amount / terms.target_amount).quantize(SHARE_PRECISION)
        if terms.target_amount > 0
        else Decimal("0.0000")
    )
    share = min(share, Decimal("1.0000"))

    if terms.target_date is None:
        # An open-ended goal has no schedule, so it cannot be behind one.
        return GoalProgress(
            as_of=today,
            current_amount=quantize_money(terms.current_amount),
            target_amount=quantize_money(terms.target_amount),
            progress_share=share,
            expected_amount=None,
            ahead_by=None,
            on_track=None,
        )

    total_days = (terms.target_date - terms.started_on).days
    elapsed_days = (today - terms.started_on).days
    if total_days <= 0:
        elapsed_share = ONE
    else:
        elapsed_share = max(min(Decimal(elapsed_days) / Decimal(total_days), ONE), Decimal(0))

    # The line runs from what was already saved when the goal started, not from zero.
    expected = quantize_money(
        terms.initial_amount + (terms.target_amount - terms.initial_amount) * elapsed_share
    )
    return GoalProgress(
        as_of=today,
        current_amount=quantize_money(terms.current_amount),
        target_amount=quantize_money(terms.target_amount),
        progress_share=share,
        expected_amount=expected,
        ahead_by=quantize_money(terms.current_amount - expected),
        on_track=terms.current_amount >= expected,
    )
