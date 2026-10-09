"""The `accounts` table."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from compass_api.db.base import Base, TimestampMixin
from compass_api.domain.money import CURRENCY_CODE_LENGTH, MONEY_PRECISION, MONEY_SCALE
from compass_api.domain.open_finance import AccountType

if TYPE_CHECKING:
    from compass_api.db.models.financial_institution import FinancialInstitution


class Account(Base, TimestampMixin):
    """An account the user holds at an institution.

    Scoped by `user_id`: every read path filters on it, so isolation is a property of
    the schema rather than something authentication will have to retrofit.
    """

    __tablename__ = "accounts"
    __table_args__ = (
        # One row per account per provider, per user: what makes ingestion idempotent.
        UniqueConstraint("user_id", "provider", "external_id"),
        Index("ix_accounts_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("financial_institutions.id", ondelete="RESTRICT"), nullable=False
    )

    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(128))

    # Stored as VARCHAR with a CHECK constraint rather than a native PostgreSQL enum:
    # adding a value later is an ordinary migration instead of an ALTER TYPE that cannot
    # run inside a transaction.
    type: Mapped[AccountType] = mapped_column(
        Enum(
            AccountType,
            native_enum=False,
            create_constraint=True,
            length=20,
            name="account_type",
            validate_strings=True,
        )
    )
    name: Mapped[str] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(CURRENCY_CODE_LENGTH))

    #: Balance as last reported by the provider. Signed: negative on a credit card means
    #: money owed.
    current_balance: Mapped[Decimal] = mapped_column(Numeric(MONEY_PRECISION, MONEY_SCALE))
    #: When that balance was read from the provider.
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # lazy="raise_on_sql": under asyncio an implicit lazy load raises a confusing
    # greenlet error at an arbitrary point. Failing loudly at the access site forces
    # callers to say what they want loaded (see the repositories).
    institution: Mapped[FinancialInstitution] = relationship(lazy="raise_on_sql")
