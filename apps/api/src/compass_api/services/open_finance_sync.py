"""Ingesting a user's financial data from an Open Finance provider.

This is the only place that knows what "syncing a user" means. It is handed a provider
(any implementation of the protocol - the sandbox mock today, a real vendor adapter
later) and persists what that provider reports.

The operation is **idempotent**: running it twice over overlapping windows updates the
existing rows instead of duplicating them, because the provider's own identifiers are
the conflict keys. That matters well beyond tidiness - a duplicated salary credit would
silently inflate every cash-flow figure computed from it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.providers.open_finance.base import OpenFinanceProvider
from compass_api.repositories.accounts import AccountRepository
from compass_api.repositories.institutions import InstitutionRepository
from compass_api.repositories.transactions import TransactionRepository
from compass_api.repositories.users import UserRepository

logger = logging.getLogger(__name__)

#: How far back a sync reaches when the caller does not say. Six months is enough history
#: for the cash-flow and recurring-expense analysis that later phases depend on.
DEFAULT_WINDOW_DAYS = 180


class UnknownUserError(LookupError):
    """The user does not exist, so there is nothing to attach ingested data to."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(str(user_id))
        self.user_id = user_id


@dataclass(frozen=True, slots=True)
class SyncReport:
    """What a single sync did. Counts only - never the financial data itself."""

    provider: str
    user_id: uuid.UUID
    since: date
    until: date
    institutions: int
    accounts: int
    accounts_created: int
    transactions: int
    transactions_created: int

    @property
    def transactions_updated(self) -> int:
        return self.transactions - self.transactions_created


class OpenFinanceSyncService:
    """Pulls accounts and transactions for one user and stores them."""

    def __init__(self, session: AsyncSession, provider: OpenFinanceProvider) -> None:
        self._session = session
        self._provider = provider
        self._users = UserRepository(session)
        self._institutions = InstitutionRepository(session)
        self._accounts = AccountRepository(session)
        self._transactions = TransactionRepository(session)

    async def sync_user(
        self,
        user_id: uuid.UUID,
        *,
        since: date | None = None,
        until: date | None = None,
    ) -> SyncReport:
        """Ingest the user's data for `[since, until]` and report what changed.

        Raises:
            UnknownUserError: if no such user exists.
            ValueError: if the window is inverted.
        """
        if await self._users.get(user_id) is None:
            raise UnknownUserError(user_id)

        until = until or date.today()
        since = since or until - timedelta(days=DEFAULT_WINDOW_DAYS)
        if since > until:
            raise ValueError("since must not be later than until")

        provider_name = self._provider.name
        synced_at = datetime.now(tz=UTC)

        # Read what is already stored before writing, so the report can distinguish a
        # first import from a refresh without resorting to dialect tricks.
        known_accounts = await self._accounts.external_ids_for_user(user_id, provider_name)
        known_transactions = await self._transactions.external_ids_for_user(user_id, provider_name)

        institutions = await self._provider.get_institutions(user_id)
        institution_ids = await self._institutions.upsert_many(provider_name, institutions)

        accounts = await self._provider.get_accounts(user_id)
        account_ids = await self._accounts.upsert_many(
            user_id=user_id,
            provider=provider_name,
            snapshots=accounts,
            institution_ids=institution_ids,
            synced_at=synced_at,
        )

        transactions = await self._provider.get_transactions(user_id, since, until)
        written = await self._transactions.upsert_many(
            user_id=user_id,
            provider=provider_name,
            snapshots=transactions,
            account_ids=account_ids,
            synced_at=synced_at,
        )

        await self._session.commit()

        report = SyncReport(
            provider=provider_name,
            user_id=user_id,
            since=since,
            until=until,
            institutions=len(institution_ids),
            accounts=len(account_ids),
            accounts_created=len(set(account_ids) - known_accounts),
            transactions=written,
            transactions_created=len(
                {snapshot.external_id for snapshot in transactions} - known_transactions
            ),
        )
        # Counts and identifiers only: no amounts, descriptions or merchants in the logs.
        logger.info(
            "open finance sync completed",
            extra={
                "user_id": str(user_id),
                "provider": provider_name,
                "since": since.isoformat(),
                "until": until.isoformat(),
                "accounts": report.accounts,
                "transactions": report.transactions,
                "transactions_created": report.transactions_created,
            },
        )
        return report
