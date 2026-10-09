"""Reads and writes for `transactions`."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.db.models import Account, Transaction
from compass_api.domain.analysis import Movement
from compass_api.domain.categories import Categorization
from compass_api.domain.open_finance import TransactionSnapshot

#: Chunk size for the upsert. One statement per chunk keeps a large backfill off a
#: single enormous query without turning it into a row-at-a-time loop.
UPSERT_CHUNK_SIZE = 500


class UnknownAccountError(LookupError):
    """A snapshot referenced an account that was not ingested with it."""


class TransactionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(
        self,
        *,
        user_id: uuid.UUID,
        provider: str,
        snapshots: Sequence[TransactionSnapshot],
        account_ids: Mapping[str, uuid.UUID],
        categorizations: Mapping[str, Categorization],
        synced_at: datetime,
    ) -> int:
        """Insert or refresh transactions, returning how many rows were written.

        Conflicts on `(account_id, provider, external_id)` update in place, so re-syncing
        an overlapping window is safe: the provider's identifier is the idempotency key.
        Refreshing also re-applies the stored category, which is how a change to the
        categorisation rules reaches rows that were ingested under the old ones.

        The caller supplies one categorization per snapshot, keyed by `external_id`; a
        missing entry is a programming error and raises.
        """
        if not snapshots:
            return 0

        rows = []
        for snapshot in snapshots:
            account_id = account_ids.get(snapshot.account_external_id)
            if account_id is None:
                raise UnknownAccountError(snapshot.account_external_id)
            categorization = categorizations[snapshot.external_id]
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "account_id": account_id,
                    "provider": provider,
                    "external_id": snapshot.external_id,
                    "booked_at": snapshot.booked_at,
                    "amount": snapshot.amount,
                    "currency": snapshot.currency,
                    "description": snapshot.description,
                    "merchant_name": snapshot.merchant_name,
                    "provider_category": snapshot.provider_category,
                    "category": categorization.category,
                    "category_rule": categorization.rule,
                    "synced_at": synced_at,
                }
            )

        excluded = insert(Transaction).excluded
        written = 0
        for start in range(0, len(rows), UPSERT_CHUNK_SIZE):
            chunk = rows[start : start + UPSERT_CHUNK_SIZE]
            statement = (
                insert(Transaction)
                .values(chunk)
                .on_conflict_do_update(
                    index_elements=["account_id", "provider", "external_id"],
                    set_={
                        "booked_at": excluded.booked_at,
                        "amount": excluded.amount,
                        "currency": excluded.currency,
                        "description": excluded.description,
                        "merchant_name": excluded.merchant_name,
                        "provider_category": excluded.provider_category,
                        "category": excluded.category,
                        "category_rule": excluded.category_rule,
                        "synced_at": excluded.synced_at,
                        "updated_at": func.now(),
                    },
                )
                .returning(Transaction.id)
            )
            written += len((await self._session.execute(statement)).all())
        return written

    def _scoped(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID | None,
        since: date | None,
        until: date | None,
    ) -> Select[Transaction]:
        statement = select(Transaction).where(Transaction.user_id == user_id)
        if account_id is not None:
            statement = statement.where(Transaction.account_id == account_id)
        if since is not None:
            statement = statement.where(Transaction.booked_at >= since)
        if until is not None:
            statement = statement.where(Transaction.booked_at <= until)
        return statement

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None = None,
        since: date | None = None,
        until: date | None = None,
        limit: int,
        offset: int = 0,
    ) -> Sequence[Transaction]:
        """A page of the user's transactions, most recent first."""
        statement = (
            self._scoped(user_id, account_id, since, until)
            .order_by(Transaction.booked_at.desc(), Transaction.external_id.desc())
            .limit(limit)
            .offset(offset)
        )
        return (await self._session.execute(statement)).scalars().all()

    async def count_for_user(
        self,
        user_id: uuid.UUID,
        *,
        account_id: uuid.UUID | None = None,
        since: date | None = None,
        until: date | None = None,
    ) -> int:
        """Total matching rows, for pagination metadata."""
        scoped = self._scoped(user_id, account_id, since, until).subquery()
        return (await self._session.execute(select(func.count()).select_from(scoped))).scalar_one()

    async def movements_for_user(
        self, user_id: uuid.UUID, *, since: date, until: date
    ) -> Sequence[Movement]:
        """The window as the financial engine consumes it.

        Returns domain `Movement` values rather than ORM rows: the engine must not be
        able to depend on persistence, and the account type it needs lives one join away.
        """
        statement = (
            select(
                Transaction.id,
                Transaction.account_id,
                Account.type,
                Transaction.booked_at,
                Transaction.amount,
                Transaction.category,
                Transaction.description,
                Transaction.merchant_name,
            )
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.user_id == user_id,
                Transaction.booked_at >= since,
                Transaction.booked_at <= until,
            )
            .order_by(Transaction.booked_at, Transaction.external_id)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            Movement(
                id=row.id,
                account_id=row.account_id,
                account_type=row.type,
                booked_at=row.booked_at,
                amount=row.amount,
                category=row.category,
                description=row.description,
                merchant_name=row.merchant_name,
            )
            for row in rows
        ]

    async def external_ids_for_user(self, user_id: uuid.UUID, provider: str) -> set[str]:
        """Provider ids already stored, so a sync can report what it created."""
        statement = select(Transaction.external_id).where(
            Transaction.user_id == user_id, Transaction.provider == provider
        )
        return set((await self._session.execute(statement)).scalars().all())
