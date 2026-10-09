"""Repository queries: scoping, filtering, pagination."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from compass_api.db.models import User
from compass_api.providers.open_finance import MockOpenFinanceProvider
from compass_api.repositories.accounts import AccountRepository
from compass_api.repositories.transactions import TransactionRepository
from compass_api.services.open_finance_sync import OpenFinanceSyncService
from tests.integration.conftest import REFERENCE_DATE, WINDOW_END, WINDOW_START

pytestmark = pytest.mark.integration


@pytest.fixture
async def ingested(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
) -> User:
    async with sessionmaker() as session:
        await OpenFinanceSyncService(session, provider).sync_user(
            user.id, since=WINDOW_START, until=WINDOW_END
        )
    return user


async def test_accounts_are_listed_with_their_institution(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User
) -> None:
    async with sessionmaker() as session:
        accounts = await AccountRepository(session).list_for_user(ingested.id)

    assert len(accounts) == 3
    # The relationship is lazy="raise_on_sql", so reading it proves it was eager-loaded.
    assert all(account.institution.name for account in accounts)
    assert all(account.currency == "BRL" for account in accounts)
    assert all(isinstance(account.current_balance, Decimal) for account in accounts)


async def test_get_account_is_scoped_to_its_owner(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User, other_user: User
) -> None:
    async with sessionmaker() as session:
        repository = AccountRepository(session)
        accounts = await repository.list_for_user(ingested.id)
        account_id = accounts[0].id

        assert await repository.get_for_user(ingested.id, account_id) is not None
        assert await repository.get_for_user(other_user.id, account_id) is None


async def test_unknown_account_id_reads_as_missing(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User
) -> None:
    async with sessionmaker() as session:
        assert await AccountRepository(session).get_for_user(ingested.id, uuid.uuid4()) is None


async def test_transactions_are_filtered_by_account(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User
) -> None:
    async with sessionmaker() as session:
        account = (await AccountRepository(session).list_for_user(ingested.id))[0]
        repository = TransactionRepository(session)

        total = await repository.count_for_user(ingested.id)
        for_account = await repository.count_for_user(ingested.id, account_id=account.id)
        rows = await repository.list_for_user(ingested.id, account_id=account.id, limit=500)

    assert 0 < for_account < total
    assert len(rows) == for_account
    assert {row.account_id for row in rows} == {account.id}


async def test_transactions_are_filtered_by_window(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User
) -> None:
    async with sessionmaker() as session:
        repository = TransactionRepository(session)
        rows = await repository.list_for_user(
            ingested.id, since=REFERENCE_DATE.replace(day=1), until=REFERENCE_DATE, limit=500
        )

    assert rows
    assert all(REFERENCE_DATE.replace(day=1) <= row.booked_at <= REFERENCE_DATE for row in rows)


async def test_transactions_are_ordered_most_recent_first(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User
) -> None:
    async with sessionmaker() as session:
        rows = await TransactionRepository(session).list_for_user(ingested.id, limit=20)

    booked = [row.booked_at for row in rows]
    assert booked == sorted(booked, reverse=True)


async def test_pagination_walks_the_whole_result_without_repeating(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User
) -> None:
    page_size = 25
    async with sessionmaker() as session:
        repository = TransactionRepository(session)
        total = await repository.count_for_user(ingested.id)

        seen: list[uuid.UUID] = []
        for offset in range(0, total, page_size):
            page = await repository.list_for_user(ingested.id, limit=page_size, offset=offset)
            seen.extend(row.id for row in page)

    assert len(seen) == total
    assert len(set(seen)) == total


async def test_transactions_of_another_user_are_invisible(
    sessionmaker: async_sessionmaker[AsyncSession], ingested: User, other_user: User
) -> None:
    async with sessionmaker() as session:
        repository = TransactionRepository(session)

        assert await repository.count_for_user(ingested.id) > 0
        assert await repository.count_for_user(other_user.id) == 0
        assert await repository.list_for_user(other_user.id, limit=10) == []
