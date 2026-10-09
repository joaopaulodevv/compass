"""Ingestion from an Open Finance provider.

The property that matters here is idempotency. A duplicated salary credit would inflate
every cash-flow figure computed from it, silently and forever, so re-syncing an
overlapping window must update rows rather than add them.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from compass_api.db.models import Account, Transaction, User
from compass_api.providers.open_finance import MockOpenFinanceProvider
from compass_api.services.open_finance_sync import (
    OpenFinanceSyncService,
    SyncReport,
    UnknownUserError,
)
from tests.integration.conftest import REFERENCE_DATE, WINDOW_END, WINDOW_START

pytestmark = pytest.mark.integration


async def _sync(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
    *,
    since: date = WINDOW_START,
    until: date = WINDOW_END,
) -> SyncReport:
    async with sessionmaker() as session:
        service = OpenFinanceSyncService(session, provider)
        return await service.sync_user(user.id, since=since, until=until)


async def _count(
    sessionmaker: async_sessionmaker[AsyncSession],
    model: type[Account] | type[Transaction],
    user: User,
) -> int:
    async with sessionmaker() as session:
        statement = select(func.count()).select_from(model).where(model.user_id == user.id)
        return (await session.execute(statement)).scalar_one()


async def test_sync_persists_accounts_and_transactions(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
) -> None:
    report = await _sync(sessionmaker, provider, user)

    expected = len(await provider.get_transactions(user.id, WINDOW_START, WINDOW_END))
    assert expected >= 90, "the fixture should hold several months of history"
    assert report.accounts == 3
    assert report.accounts_created == 3
    assert report.transactions == expected
    assert report.transactions_created == expected
    assert report.transactions_updated == 0
    assert await _count(sessionmaker, Account, user) == 3
    assert await _count(sessionmaker, Transaction, user) == expected


async def test_sync_is_idempotent(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
) -> None:
    first = await _sync(sessionmaker, provider, user)
    second = await _sync(sessionmaker, provider, user)

    assert second.accounts_created == 0
    assert second.transactions_created == 0
    assert second.transactions_updated == first.transactions
    assert await _count(sessionmaker, Transaction, user) == first.transactions
    assert await _count(sessionmaker, Account, user) == first.accounts


async def test_overlapping_windows_do_not_duplicate(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
) -> None:
    """The realistic case: a scheduled sync re-reads the last few weeks every time."""
    await _sync(sessionmaker, provider, user)
    overlap_start = REFERENCE_DATE - timedelta(days=45)

    await _sync(sessionmaker, provider, user, since=overlap_start, until=WINDOW_END)

    full_window = len(await provider.get_transactions(user.id, WINDOW_START, WINDOW_END))
    assert await _count(sessionmaker, Transaction, user) == full_window


async def test_sync_respects_the_requested_window(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
) -> None:
    since = REFERENCE_DATE - timedelta(days=30)

    report = await _sync(sessionmaker, provider, user, since=since, until=REFERENCE_DATE)

    assert (
        0
        < report.transactions
        < len(await provider.get_transactions(user.id, WINDOW_START, WINDOW_END))
    )
    async with sessionmaker() as session:
        booked = (
            await session.execute(
                select(Transaction.booked_at).where(Transaction.user_id == user.id)
            )
        ).scalars()
        assert all(since <= day <= REFERENCE_DATE for day in booked)


async def test_each_user_gets_their_own_rows(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
    other_user: User,
) -> None:
    """The sandbox serves identical data to both, so only `user_id` separates them."""
    first = await _sync(sessionmaker, provider, user)
    second = await _sync(sessionmaker, provider, other_user)

    assert second.accounts_created == 3, "another user's accounts must not be reused"
    assert second.transactions_created == first.transactions
    assert await _count(sessionmaker, Transaction, user) == first.transactions
    assert await _count(sessionmaker, Transaction, other_user) == second.transactions

    async with sessionmaker() as session:
        ids = (
            (await session.execute(select(Account.id).where(Account.user_id == user.id)))
            .scalars()
            .all()
        )
        other_ids = (
            (await session.execute(select(Account.id).where(Account.user_id == other_user.id)))
            .scalars()
            .all()
        )
    assert not set(ids) & set(other_ids)


async def test_institutions_are_shared_between_users(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
    other_user: User,
) -> None:
    """Two users at the same bank point at one institution row, not two."""
    await _sync(sessionmaker, provider, user)
    await _sync(sessionmaker, provider, other_user)

    async with sessionmaker() as session:
        institutions = (
            (
                await session.execute(
                    select(Account.institution_id).where(
                        Account.user_id.in_([user.id, other_user.id])
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(set(institutions)) == 2, "the fixture has two institutions"


async def test_unknown_user_is_rejected(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
) -> None:
    async with sessionmaker() as session:
        service = OpenFinanceSyncService(session, provider)
        with pytest.raises(UnknownUserError):
            await service.sync_user(uuid.uuid4())


async def test_inverted_window_is_rejected(
    sessionmaker: async_sessionmaker[AsyncSession],
    provider: MockOpenFinanceProvider,
    user: User,
) -> None:
    async with sessionmaker() as session:
        service = OpenFinanceSyncService(session, provider)
        with pytest.raises(ValueError, match="since"):
            await service.sync_user(user.id, since=WINDOW_END, until=WINDOW_START)
