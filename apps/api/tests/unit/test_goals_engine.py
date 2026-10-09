"""The goal engine.

Pure arithmetic, so every expectation here was worked out by hand. The worked example
throughout is the one from the product brief: R$ 20,000 for a trip in 18 months.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from compass_api.domain.goals import GoalPathOption, GoalTerms
from compass_api.services import goals_engine as engine

TODAY = date(2026, 6, 15)
IN_18_MONTHS = date(2027, 12, 15)


def terms(
    target: str = "20000.00",
    current: str = "0.00",
    *,
    target_date: date | None = IN_18_MONTHS,
    started_on: date = TODAY,
    initial: str = "0.00",
) -> GoalTerms:
    """`initial` defaults to zero: these tests measure growth from nothing unless they
    say otherwise, which is what the progress assertions are about."""
    return GoalTerms(
        target_amount=Decimal(target),
        current_amount=Decimal(current),
        started_on=started_on,
        target_date=target_date,
        initial_amount=Decimal(initial),
    )


# --- rate conversion -----------------------------------------------------------------


def test_annual_rate_converts_to_an_effective_monthly_rate() -> None:
    """Twelve months of the monthly rate must compound back to the annual rate."""
    monthly = engine.monthly_rate(Decimal("0.12"))

    assert (Decimal(1) + monthly) ** 12 == pytest.approx(Decimal("1.12"))
    # Dividing by twelve would overstate it, and so flatter every projection.
    assert monthly < Decimal("0.12") / 12


def test_a_zero_rate_stays_exactly_zero() -> None:
    assert engine.monthly_rate(Decimal("0")) == Decimal(0)


# --- simulate ------------------------------------------------------------------------


def test_simulation_without_returns_is_plain_division() -> None:
    simulation = engine.simulate(terms(), Decimal("1000.00"), as_of=TODAY)

    assert simulation.months_to_target == 20
    assert simulation.projected_completion == date(2028, 2, 15)
    assert simulation.total_contributed == Decimal("20000.00")
    assert simulation.total_return == Decimal("0.00")
    assert simulation.is_feasible


def test_a_remainder_rounds_up_to_a_whole_month() -> None:
    """Nineteen and a bit months of contributions means twenty months of saving."""
    simulation = engine.simulate(terms(), Decimal("1050.00"), as_of=TODAY)

    assert simulation.months_to_target == 20
    assert simulation.projected_amount == Decimal("21000.00")


def test_returns_shorten_the_wait_and_are_reported_separately() -> None:
    simulation = engine.simulate(terms(), Decimal("1000.00"), Decimal("0.10"), as_of=TODAY)

    assert simulation.months_to_target == 19
    assert simulation.total_contributed == Decimal("19000.00")
    assert simulation.total_return > 0
    assert simulation.projected_amount == simulation.total_contributed + simulation.total_return


def test_an_already_reached_goal_takes_no_months() -> None:
    simulation = engine.simulate(terms(current="20000.00"), Decimal("500.00"), as_of=TODAY)

    assert simulation.months_to_target == 0
    assert simulation.projected_completion == TODAY
    assert simulation.total_contributed == Decimal("0.00")


def test_contributing_nothing_with_no_return_never_arrives() -> None:
    simulation = engine.simulate(terms(), Decimal("0.00"), as_of=TODAY)

    assert simulation.months_to_target is None
    assert simulation.projected_completion is None
    assert not simulation.is_feasible


def test_an_existing_balance_counts_towards_the_target() -> None:
    simulation = engine.simulate(terms(current="10000.00"), Decimal("1000.00"), as_of=TODAY)

    assert simulation.months_to_target == 10


def test_returns_alone_can_reach_a_goal() -> None:
    """No contribution, but a balance that grows.

    Twelve months at an effective 10% a year turns 10,000 into exactly 11,000 - which
    only holds because reaching the target is judged on the balance rounded to the
    centavo, not on the full-precision residue underneath it.
    """
    simulation = engine.simulate(
        terms(target="11000.00", current="10000.00"), Decimal("0.00"), Decimal("0.10"), as_of=TODAY
    )

    assert simulation.months_to_target == 12
    assert simulation.projected_amount == Decimal("11000.00")
    assert simulation.total_contributed == Decimal("0.00")
    assert simulation.total_return > 0


# --- required contribution -----------------------------------------------------------


def test_required_contribution_reaches_the_target_when_paid() -> None:
    """The point of rounding a requirement up: paying it exactly must be enough."""
    required = engine.required_monthly(terms(), 18)

    assert required == Decimal("1111.12")
    assert required * 18 >= Decimal("20000.00")


def test_required_contribution_accounts_for_what_is_already_saved() -> None:
    assert engine.required_monthly(terms(current="2000.00"), 18) == Decimal("1000.00")


def test_required_contribution_falls_with_an_expected_return() -> None:
    without = engine.required_monthly(terms(), 18)
    with_return = engine.required_monthly(terms(), 18, Decimal("0.10"))

    assert with_return < without


def test_required_contribution_agrees_with_the_simulation() -> None:
    """Two different code paths over the same definition must not disagree."""
    for rate in (Decimal("0"), Decimal("0.06"), Decimal("0.11")):
        required = engine.required_monthly(terms(), 18, rate)
        projected = engine.project_balance(terms(), required, rate, 18)
        assert projected >= Decimal("20000.00")


def test_nothing_is_required_for_a_goal_already_met() -> None:
    assert engine.required_monthly(terms(current="25000.00"), 18) == Decimal("0.00")


def test_with_no_months_left_the_whole_remainder_is_required_at_once() -> None:
    assert engine.required_monthly(terms(current="5000.00"), 0) == Decimal("15000.00")


def test_an_existing_balance_that_will_grow_past_the_target_requires_nothing() -> None:
    assert engine.required_monthly(
        terms(target="10500.00", current="10000.00"), 12, Decimal("0.10")
    ) == Decimal("0.00")


# --- gap -----------------------------------------------------------------------------


def test_gap_reports_what_is_missing() -> None:
    shortfall = engine.gap(terms(), Decimal("900.00"), as_of=TODAY)

    assert shortfall.months_available == 18
    assert shortfall.required_monthly == Decimal("1111.12")
    assert shortfall.planned_monthly == Decimal("900.00")
    assert shortfall.projected_amount == Decimal("16200.00")
    assert shortfall.shortfall_total == Decimal("3800.00")
    assert shortfall.shortfall_monthly == Decimal("211.12")
    assert not shortfall.on_track


def test_a_sufficient_contribution_is_on_track_with_nothing_missing() -> None:
    shortfall = engine.gap(terms(), Decimal("1111.12"), as_of=TODAY)

    assert shortfall.on_track
    assert shortfall.shortfall_total == Decimal("0.00")
    assert shortfall.shortfall_monthly == Decimal("0.00")


def test_an_undated_goal_has_no_gap_to_measure() -> None:
    with pytest.raises(ValueError, match="target date"):
        engine.gap(terms(target_date=None), Decimal("500.00"), as_of=TODAY)


def test_an_overdue_goal_needs_the_remainder_now() -> None:
    overdue = terms(current="5000.00", target_date=date(2026, 1, 15), started_on=date(2025, 6, 15))

    shortfall = engine.gap(overdue, Decimal("900.00"), as_of=TODAY)

    assert shortfall.months_available == 0
    assert shortfall.required_monthly == Decimal("15000.00")
    assert shortfall.projected_amount == Decimal("5000.00")
    assert not shortfall.on_track


# --- compare paths -------------------------------------------------------------------


def test_paths_are_ordered_by_how_soon_the_goal_is_reached() -> None:
    paths = engine.compare_paths(
        terms(),
        [
            GoalPathOption("stretch", Decimal("1500.00")),
            GoalPathOption("comfortable", Decimal("900.00")),
            GoalPathOption("with return", Decimal("900.00"), Decimal("0.11")),
        ],
        as_of=TODAY,
    )

    assert [path.label for path in paths] == ["stretch", "with return", "comfortable"]
    assert [path.simulation.months_to_target for path in paths] == [14, 21, 23]


def test_unreachable_paths_are_listed_last_rather_than_hidden() -> None:
    paths = engine.compare_paths(
        terms(),
        [
            GoalPathOption("nothing", Decimal("0.00")),
            GoalPathOption("something", Decimal("500.00")),
        ],
        as_of=TODAY,
    )

    assert [path.label for path in paths] == ["something", "nothing"]
    assert paths[-1].simulation.months_to_target is None


# --- progress ------------------------------------------------------------------------


def test_progress_compares_against_the_straight_line_to_the_target_date() -> None:
    """Six of eighteen months in, a third of the way is roughly where one should be."""
    halfway = engine.progress(terms(current="5000.00"), as_of=date(2026, 12, 15))

    assert halfway.progress_share == Decimal("0.2500")
    assert halfway.expected_amount == Decimal("6678.83")
    assert halfway.ahead_by == Decimal("-1678.83")
    assert halfway.on_track is False


def test_being_ahead_is_reported_as_a_positive_number() -> None:
    ahead = engine.progress(terms(current="13000.00"), as_of=date(2026, 12, 15))

    assert ahead.ahead_by is not None
    assert ahead.ahead_by > 0
    assert ahead.on_track is True


def test_the_line_starts_from_what_was_already_saved() -> None:
    """A goal created with R$ 5,000 already aside is not behind on day one."""
    with_initial = terms(current="5000.00", initial="5000.00")

    assert engine.progress(with_initial, as_of=TODAY).on_track is True
    assert engine.progress(with_initial, as_of=TODAY).expected_amount == Decimal("5000.00")


def test_an_undated_goal_cannot_be_behind_a_schedule_it_does_not_have() -> None:
    open_ended = engine.progress(terms(current="5000.00", target_date=None), as_of=TODAY)

    assert open_ended.progress_share == Decimal("0.2500")
    assert open_ended.expected_amount is None
    assert open_ended.ahead_by is None
    assert open_ended.on_track is None


def test_progress_share_never_exceeds_one() -> None:
    overshot = engine.progress(terms(current="25000.00"), as_of=date(2026, 12, 15))

    assert overshot.progress_share == Decimal("1.0000")


def test_a_goal_whose_deadline_is_its_start_is_due_in_full_immediately() -> None:
    """A degenerate window the API rejects at creation but data can still reach."""
    due_now = terms(current="5000.00", target_date=TODAY, started_on=TODAY)

    now = engine.progress(due_now, as_of=TODAY)

    assert now.expected_amount == Decimal("20000.00")
    assert now.ahead_by == Decimal("-15000.00")
    assert now.on_track is False
