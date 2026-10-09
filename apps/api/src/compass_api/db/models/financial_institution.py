"""The `financial_institutions` table."""

from __future__ import annotations

import uuid

from sqlalchemy import String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from compass_api.db.base import Base, TimestampMixin


class FinancialInstitution(Base, TimestampMixin):
    """A bank or issuer, as identified by an Open Finance provider.

    Institutions are shared across users: two users banking at the same institution
    reference the same row. Nothing user-specific belongs here.
    """

    __tablename__ = "financial_institutions"
    __table_args__ = (UniqueConstraint("provider", "external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    #: Which adapter supplied this row (`OpenFinanceProvider.name`).
    provider: Mapped[str] = mapped_column(String(32))
    #: The provider's own identifier. Unique per provider, not globally.
    external_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
