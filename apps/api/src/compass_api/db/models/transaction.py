"""The `transactions` table."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from compass_api.db.base import Base, TimestampMixin
from compass_api.domain.money import (
    CURRENCY_CODE_LENGTH,
    MONEY_PRECISION,
    MONEY_SCALE,
    Direction,
)


class Transaction(Base, TimestampMixin):
    """A single movement on an account.

    `amount` is signed - negative is an outflow - so aggregating a window is a sum with
    no direction branch (see `compass_api.domain.money`).
    """

    __tablename__ = "transactions"
    __table_args__ = (
        # The provider's identifier is the idempotency key: re-syncing an overlapping
        # window updates rows instead of duplicating them.
        UniqueConstraint("account_id", "provider", "external_id"),
        # Every analytical query is "this user's transactions over this window".
        Index("ix_transactions_user_id_booked_at", "user_id", "booked_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    # user_id is denormalised from accounts on purpose: it keeps the isolation filter on
    # the same row as the data and spares every cash-flow query a join. The cost is one
    # redundant column that ingestion must set correctly, which a test covers.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )

    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))

    #: The date the provider booked the movement.
    booked_at: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    currency: Mapped[str] = mapped_column(String(CURRENCY_CODE_LENGTH))

    description: Mapped[str] = mapped_column(String(512))
    merchant_name: Mapped[str | None] = mapped_column(String(255), default=None)
    #: The provider's own label. Compass's categorisation is a later phase and will live
    #: in its own column, so the raw value stays auditable.
    provider_category: Mapped[str | None] = mapped_column(String(128), default=None)

    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    @property
    def direction(self) -> Direction:
        """Derived from the sign of `amount`; never stored."""
        return Direction.of(self.amount)
