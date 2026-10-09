"""The `financial_goals` table."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from compass_api.db.base import Base, TimestampMixin
from compass_api.domain.goals import GoalStatus, GoalTerms
from compass_api.domain.money import MONEY_PRECISION, MONEY_SCALE


class FinancialGoal(Base, TimestampMixin):
    """Something the user is saving for.

    Only the terms are stored. Every derived figure - how long it takes, what the date
    demands, whether the user is ahead - is computed on request by the pure engine, so a
    stale projection can never be served (ADR-0008).
    """

    __tablename__ = "financial_goals"
    __table_args__ = (
        UniqueConstraint("user_id", "name"),
        CheckConstraint("target_amount > 0", name="target_amount_positive"),
        CheckConstraint("current_amount >= 0 AND initial_amount >= 0", name="amounts_not_negative"),
        CheckConstraint(
            "monthly_contribution IS NULL OR monthly_contribution >= 0",
            name="contribution_not_negative",
        ),
        Index("ix_financial_goals_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[Decimal] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    #: Optional: a goal may be "as soon as possible" rather than "by a date".
    target_date: Mapped[date | None] = mapped_column(Date, default=None)

    #: What was already set aside when the goal was created. The straight line that
    #: progress is measured against starts here, not at zero.
    initial_amount: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), default=Decimal("0.00")
    )
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), default=Decimal("0.00")
    )
    #: What the user plans to put in each month. When absent, forecasts fall back to the
    #: saving capacity measured from their own history.
    monthly_contribution: Mapped[Decimal | None] = mapped_column(
        Numeric(MONEY_PRECISION, MONEY_SCALE), default=None
    )

    started_on: Mapped[date] = mapped_column(Date)
    status: Mapped[GoalStatus] = mapped_column(
        Enum(
            GoalStatus,
            native_enum=False,
            create_constraint=True,
            length=16,
            name="goal_status",
            validate_strings=True,
        ),
        default=GoalStatus.ACTIVE,
    )

    @property
    def terms(self) -> GoalTerms:
        """The engine's view of this goal."""
        return GoalTerms(
            target_amount=self.target_amount,
            current_amount=self.current_amount,
            started_on=self.started_on,
            target_date=self.target_date,
            initial_amount=self.initial_amount,
        )
