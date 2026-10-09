"""Goals: persistence, and running the engine over them.

The split is the same as everywhere else. `goals_engine` is pure arithmetic and knows
nothing about users or databases; the repository knows nothing about finance; this
service joins them, decides which contribution a forecast should assume, and owns the
one business rule a goal has - a goal whose balance reaches its target is achieved.

Where a forecast's contribution comes from is reported alongside the numbers. "You could
save R$ 3,784 a month" means something different when it is measured from six months of
the user's own history than when they typed it in, and the answer should say which.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.db.models import FinancialGoal
from compass_api.domain.goals import (
    GoalGap,
    GoalPath,
    GoalPathOption,
    GoalProgress,
    GoalSimulation,
    GoalStatus,
    GoalTerms,
)
from compass_api.repositories.goals import GoalRepository
from compass_api.repositories.users import UserRepository
from compass_api.services import goals_engine
from compass_api.services.insights import AnalysisWindow, InsightsService

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")


class UnknownUserError(LookupError):
    """The user does not exist, so there is nothing to attach a goal to."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(str(user_id))
        self.user_id = user_id


class ContributionSource(StrEnum):
    """Where the monthly contribution in a forecast came from."""

    #: The caller asked for this figure explicitly.
    REQUESTED = "requested"
    #: The goal's own plan, as the user set it.
    GOAL_PLAN = "goal_plan"
    #: Measured from the user's history - the median monthly net (ADR-0009).
    MEASURED_CAPACITY = "measured_capacity"


@dataclass(frozen=True, slots=True)
class GoalDraft:
    """A goal to create."""

    name: str
    target_amount: Decimal
    target_date: date | None = None
    initial_amount: Decimal = ZERO
    monthly_contribution: Decimal | None = None
    started_on: date | None = None


@dataclass(frozen=True, slots=True)
class GoalChanges:
    """Fields to update. `None` means "leave as it is"."""

    name: str | None = None
    target_amount: Decimal | None = None
    target_date: date | None = None
    current_amount: Decimal | None = None
    monthly_contribution: Decimal | None = None
    status: GoalStatus | None = None


@dataclass(frozen=True, slots=True)
class GoalForecast:
    """Everything worth knowing about a goal right now."""

    goal: FinancialGoal
    monthly_contribution: Decimal
    contribution_source: ContributionSource
    annual_return_rate: Decimal
    simulation: GoalSimulation
    #: Only for a dated goal: without a deadline there is no gap to measure.
    gap: GoalGap | None
    progress: GoalProgress


class GoalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._goals = GoalRepository(session)
        self._users = UserRepository(session)
        self._insights = InsightsService(session)

    async def create(self, user_id: uuid.UUID, draft: GoalDraft) -> FinancialGoal:
        """Create a goal for the user.

        Raises:
            UnknownUserError: if no such user exists.
            GoalNameTakenError: if the user already has a goal with that name.
        """
        if await self._users.get(user_id) is None:
            raise UnknownUserError(user_id)

        initial = draft.initial_amount
        goal = FinancialGoal(
            user_id=user_id,
            name=draft.name,
            target_amount=draft.target_amount,
            target_date=draft.target_date,
            initial_amount=initial,
            # A new goal starts where it starts: whatever is already set aside.
            current_amount=initial,
            monthly_contribution=draft.monthly_contribution,
            started_on=draft.started_on or date.today(),
            status=GoalStatus.ACTIVE,
        )
        await self._goals.add(goal)
        await self._session.commit()
        logger.info("goal created", extra={"user_id": str(user_id), "goal_id": str(goal.id)})
        return goal

    async def list(self, user_id: uuid.UUID) -> Sequence[FinancialGoal]:
        return await self._goals.list_for_user(user_id)

    async def get(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> FinancialGoal | None:
        return await self._goals.get_for_user(user_id, goal_id)

    async def update(
        self, user_id: uuid.UUID, goal_id: uuid.UUID, changes: GoalChanges
    ) -> FinancialGoal | None:
        """Apply changes and return the goal, or `None` if the user has no such goal."""
        goal = await self._goals.get_for_user(user_id, goal_id)
        if goal is None:
            return None

        if changes.name is not None:
            goal.name = changes.name
        if changes.target_amount is not None:
            goal.target_amount = changes.target_amount
        if changes.target_date is not None:
            goal.target_date = changes.target_date
        if changes.current_amount is not None:
            goal.current_amount = changes.current_amount
        if changes.monthly_contribution is not None:
            goal.monthly_contribution = changes.monthly_contribution
        if changes.status is not None:
            goal.status = changes.status

        # The one rule a goal has: reaching the target achieves it. Applied here rather
        # than in a database trigger so it is visible and testable.
        if goal.current_amount >= goal.target_amount and goal.status is GoalStatus.ACTIVE:
            goal.status = GoalStatus.ACHIEVED

        await self._session.commit()
        return goal

    async def forecast(
        self,
        user_id: uuid.UUID,
        goal: FinancialGoal,
        *,
        monthly_contribution: Decimal | None = None,
        annual_return_rate: Decimal = Decimal("0"),
        as_of: date | None = None,
    ) -> GoalForecast:
        """Simulate the goal, measure its gap, and say where it stands."""
        contribution, source = await self._resolve_contribution(user_id, goal, monthly_contribution)
        terms = goal.terms

        return GoalForecast(
            goal=goal,
            monthly_contribution=contribution,
            contribution_source=source,
            annual_return_rate=annual_return_rate,
            simulation=goals_engine.simulate(terms, contribution, annual_return_rate, as_of=as_of),
            gap=(
                goals_engine.gap(terms, contribution, annual_return_rate, as_of=as_of)
                if terms.target_date is not None
                else None
            ),
            progress=goals_engine.progress(terms, as_of=as_of),
        )

    async def compare(
        self,
        goal: FinancialGoal,
        options: Sequence[GoalPathOption],
        *,
        as_of: date | None = None,
    ) -> tuple[GoalPath, ...]:
        """Put several contribution-and-return scenarios side by side."""
        return goals_engine.compare_paths(goal.terms, options, as_of=as_of)

    async def simulate_draft(
        self,
        user_id: uuid.UUID,
        terms: GoalTerms,
        *,
        monthly_contribution: Decimal | None = None,
        annual_return_rate: Decimal = Decimal("0"),
        as_of: date | None = None,
    ) -> tuple[Decimal, ContributionSource, GoalSimulation, GoalGap | None]:
        """Answer "what if" for a goal that does not exist yet.

        The question a user actually asks first - *"I want R$ 20,000 in 18 months, can
        I?"* - needs no record to be created.
        """
        if monthly_contribution is None:
            contribution = await self._measured_capacity(user_id)
            source = ContributionSource.MEASURED_CAPACITY
        else:
            contribution, source = monthly_contribution, ContributionSource.REQUESTED

        simulation = goals_engine.simulate(terms, contribution, annual_return_rate, as_of=as_of)
        shortfall = (
            goals_engine.gap(terms, contribution, annual_return_rate, as_of=as_of)
            if terms.target_date is not None
            else None
        )
        return contribution, source, simulation, shortfall

    async def _resolve_contribution(
        self,
        user_id: uuid.UUID,
        goal: FinancialGoal,
        requested: Decimal | None,
    ) -> tuple[Decimal, ContributionSource]:
        """Explicit request, then the goal's own plan, then measured capacity."""
        if requested is not None:
            return requested, ContributionSource.REQUESTED
        if goal.monthly_contribution is not None:
            return goal.monthly_contribution, ContributionSource.GOAL_PLAN
        return await self._measured_capacity(user_id), ContributionSource.MEASURED_CAPACITY

    async def _measured_capacity(self, user_id: uuid.UUID) -> Decimal:
        capacity = await self._insights.saving_capacity(user_id, AnalysisWindow.resolve(None, None))
        return capacity.sustainable_monthly
