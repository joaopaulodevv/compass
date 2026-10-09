"""Financial goals and the results of reasoning about them.

A goal is a target amount, optionally by a date. Everything interesting about it is
derived - how long it takes, what it would take to hit the date, whether the user is
ahead or behind - and every one of those figures comes out of the pure engine in
`services/goals.py`, never out of an LLM (ADR-0005).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class GoalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ACHIEVED = "ACHIEVED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class GoalTerms:
    """The engine's view of a goal: the numbers, with no persistence attached."""

    target_amount: Decimal
    current_amount: Decimal
    started_on: date
    target_date: date | None = None
    #: What was already set aside when the goal was created. The straight line that
    #: `progress` measures against runs from here to the target, not from zero.
    initial_amount: Decimal = Decimal("0.00")

    @property
    def remaining(self) -> Decimal:
        """How much is still missing. Never negative."""
        return max(self.target_amount - self.current_amount, Decimal("0.00"))

    @property
    def is_reached(self) -> bool:
        return self.current_amount >= self.target_amount


@dataclass(frozen=True, slots=True)
class GoalSimulation:
    """How a goal plays out at a given contribution and expected return."""

    monthly_contribution: Decimal
    annual_return_rate: Decimal
    #: None when the target is never reached within the horizon the engine will project.
    months_to_target: int | None
    projected_completion: date | None
    #: What the balance would be at `projected_completion`, or at the horizon if the
    #: target is never reached.
    projected_amount: Decimal
    total_contributed: Decimal
    total_return: Decimal

    @property
    def is_feasible(self) -> bool:
        return self.months_to_target is not None


@dataclass(frozen=True, slots=True)
class GoalGap:
    """What it would take to hit a dated target, and what is missing.

    `required_monthly` is the contribution that lands exactly on the target amount on the
    target date. `planned_monthly` is what the user actually has - their own plan, or the
    saving capacity measured from their history.
    """

    target_date: date
    months_available: int
    required_monthly: Decimal
    planned_monthly: Decimal
    projected_amount: Decimal
    #: How much would still be missing on the target date. Zero when on track.
    shortfall_total: Decimal
    #: How much more would have to be set aside each month. Zero when on track.
    shortfall_monthly: Decimal
    on_track: bool


@dataclass(frozen=True, slots=True)
class GoalPathOption:
    """One scenario to compare: a contribution and an expected return."""

    label: str
    monthly_contribution: Decimal
    annual_return_rate: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class GoalPath:
    """A compared scenario and how it turns out."""

    label: str
    simulation: GoalSimulation


@dataclass(frozen=True, slots=True)
class GoalProgress:
    """Where the goal stands today, against where it should be.

    `expected_amount` is the straight line from where the goal started to the target on
    its target date - the simplest expectation a user can check for themselves. It is
    `None` for an open-ended goal, which has no schedule to be behind.
    """

    as_of: date
    current_amount: Decimal
    target_amount: Decimal
    #: Fraction of the target reached, 0-1, rounded to four places.
    progress_share: Decimal
    expected_amount: Decimal | None
    #: Positive when ahead of the straight line, negative when behind.
    ahead_by: Decimal | None
    on_track: bool | None
