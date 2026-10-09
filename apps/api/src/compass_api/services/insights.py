"""Composing the financial engine over stored data.

The split this module exists to keep: the **engine** (`cashflow`, `recurring`,
`saving_capacity`) is pure and knows nothing about databases; the **repository** knows
nothing about finance; this service joins them and owns the window defaults. Routes call
it and do no orchestration of their own.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.domain.analysis import CashflowSummary, RecurringExpense, SavingCapacity
from compass_api.repositories.transactions import TransactionRepository
from compass_api.services import cashflow, recurring, saving_capacity

#: Default analysis window. Six months is enough for a monthly median to mean something
#: and short enough that a change in circumstances is not averaged away.
DEFAULT_WINDOW_DAYS = 180


@dataclass(frozen=True, slots=True)
class AnalysisWindow:
    """An inclusive date range to analyse."""

    since: date
    until: date

    @classmethod
    def resolve(cls, since: date | None, until: date | None) -> AnalysisWindow:
        """Fill in whichever end was not given.

        Raises:
            ValueError: if the window is inverted.
        """
        resolved_until = until or date.today()
        resolved_since = since or resolved_until - timedelta(days=DEFAULT_WINDOW_DAYS)
        if resolved_since > resolved_until:
            raise ValueError("since must not be later than until")
        return cls(since=resolved_since, until=resolved_until)


class InsightsService:
    """Read a user's movements and run the deterministic engine over them."""

    def __init__(self, session: AsyncSession) -> None:
        self._transactions = TransactionRepository(session)

    async def cashflow(self, user_id: uuid.UUID, window: AnalysisWindow) -> CashflowSummary:
        movements = await self._transactions.movements_for_user(
            user_id, since=window.since, until=window.until
        )
        return cashflow.summarize(movements, window.since, window.until)

    async def recurring_expenses(
        self, user_id: uuid.UUID, window: AnalysisWindow
    ) -> tuple[RecurringExpense, ...]:
        movements = await self._transactions.movements_for_user(
            user_id, since=window.since, until=window.until
        )
        return recurring.detect(movements)

    async def saving_capacity(self, user_id: uuid.UUID, window: AnalysisWindow) -> SavingCapacity:
        return saving_capacity.estimate(await self.cashflow(user_id, window))
