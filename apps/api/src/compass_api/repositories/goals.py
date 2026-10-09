"""Reads and writes for `financial_goals`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.db.models import FinancialGoal

UNIQUE_NAME_CONSTRAINT = "uq_financial_goals_user_id_name"


class GoalNameTakenError(ValueError):
    """The user already has a goal with that name."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


class GoalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, goal: FinancialGoal) -> FinancialGoal:
        """Persist a new goal.

        Raises:
            GoalNameTakenError: if the name collides with one of this user's goals. The
                database decides, not a prior SELECT, so two concurrent requests cannot
                both pass the check.
        """
        self._session.add(goal)
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            if UNIQUE_NAME_CONSTRAINT in str(error.orig):
                raise GoalNameTakenError(goal.name) from error
            raise
        return goal

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[FinancialGoal]:
        """The user's goals, soonest target first and undated ones last."""
        statement = (
            select(FinancialGoal)
            .where(FinancialGoal.user_id == user_id)
            .order_by(
                FinancialGoal.target_date.is_(None),
                FinancialGoal.target_date,
                FinancialGoal.name,
            )
        )
        return (await self._session.execute(statement)).scalars().all()

    async def get_for_user(self, user_id: uuid.UUID, goal_id: uuid.UUID) -> FinancialGoal | None:
        """One goal, scoped by owner so a wrong id cannot read another user's goal."""
        statement = select(FinancialGoal).where(
            FinancialGoal.user_id == user_id, FinancialGoal.id == goal_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()
