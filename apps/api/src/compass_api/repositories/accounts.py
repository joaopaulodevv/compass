"""Reads and writes for `accounts`."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from compass_api.db.models import Account
from compass_api.domain.open_finance import AccountSnapshot


class UnknownInstitutionError(LookupError):
    """A snapshot referenced an institution that was not ingested with it."""


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        snapshots: Sequence[AccountSnapshot],
        institution_ids: Mapping[str, uuid.UUID],
        synced_at: datetime,
    ) -> dict[str, uuid.UUID]:
        """Insert or refresh the user's accounts, returning `external_id -> id`."""
        if not snapshots:
            return {}

        rows = []
        for snapshot in snapshots:
            institution_id = institution_ids.get(snapshot.institution_external_id)
            if institution_id is None:
                raise UnknownInstitutionError(snapshot.institution_external_id)
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "institution_id": institution_id,
                    "provider": provider,
                    "external_id": snapshot.external_id,
                    "type": snapshot.type,
                    "name": snapshot.name,
                    "currency": snapshot.currency,
                    "current_balance": snapshot.current_balance,
                    "synced_at": synced_at,
                }
            )

        excluded = insert(Account).excluded
        statement = (
            insert(Account)
            .values(rows)
            .on_conflict_do_update(
                index_elements=["user_id", "provider", "external_id"],
                set_={
                    "institution_id": excluded.institution_id,
                    "type": excluded.type,
                    "name": excluded.name,
                    "currency": excluded.currency,
                    "current_balance": excluded.current_balance,
                    "synced_at": excluded.synced_at,
                    "updated_at": func.now(),
                },
            )
            .returning(Account.external_id, Account.id)
        )
        result = await self._session.execute(statement)
        return dict(result.all())  # rows are (external_id, id) pairs

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Account]:
        """The user's accounts with their institution eagerly loaded, newest name order."""
        statement = (
            select(Account)
            .where(Account.user_id == user_id)
            .options(selectinload(Account.institution))
            .order_by(Account.name)
        )
        return (await self._session.execute(statement)).scalars().all()

    async def get_for_user(self, user_id: uuid.UUID, account_id: uuid.UUID) -> Account | None:
        """One account, scoped by owner so a wrong id can never read another user's row."""
        statement = (
            select(Account)
            .where(Account.user_id == user_id, Account.id == account_id)
            .options(selectinload(Account.institution))
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def external_ids_for_user(self, user_id: uuid.UUID, provider: str) -> set[str]:
        """Provider ids already stored, so a sync can report what it created."""
        statement = select(Account.external_id).where(
            Account.user_id == user_id, Account.provider == provider
        )
        return set((await self._session.execute(statement)).scalars().all())
