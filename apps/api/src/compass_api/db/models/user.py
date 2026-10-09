"""The `users` table.

This is deliberately the only domain entity in Phase 1. It exists to validate the
database stack end to end and to anchor the ownership key (`user_id`) that every future
financial entity (accounts, transactions, goals, profiles, recommendations) will be
scoped by, so that data isolation is a property of the schema rather than something
bolted on when authentication arrives.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from compass_api.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(120), default=None)
