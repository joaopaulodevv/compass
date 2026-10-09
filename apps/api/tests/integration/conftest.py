"""Fixtures for tests that need a live PostgreSQL.

Everything here skips (never fails) when no database is reachable, so the suite stays
usable offline. Run `alembic upgrade head` first: these assert against the migrated
schema.

Each test gets its own user, and deleting that user at the end cascades to its accounts
and transactions - so tests cannot see each other's data, which is also a small proof
that the cascade is wired correctly.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from compass_api.api.deps import get_open_finance_provider
from compass_api.core.config import Settings, get_settings
from compass_api.db.models import User
from compass_api.main import create_app
from compass_api.providers.open_finance import MockOpenFinanceProvider

#: Pinned so every assertion about dates and windows is deterministic. The fixture holds
#: six months of history ending in this month.
REFERENCE_DATE = date(2026, 6, 15)
WINDOW_START = date(2025, 12, 1)
WINDOW_END = date(2026, 6, 30)


@pytest.fixture
async def engine(settings: Settings) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(str(settings.database_url))
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:  # Any connection problem means "skip", not "fail".
        await engine.dispose()
        pytest.skip(f"PostgreSQL is not reachable: {exc}")
    yield engine
    await engine.dispose()


@pytest.fixture
def sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def tx_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session in a transaction that is always rolled back.

    For code that does not commit. Ingestion does, so it uses `sessionmaker` instead.
    """
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as session:
            yield session
        await transaction.rollback()


async def _create_user(sessionmaker: async_sessionmaker[AsyncSession]) -> User:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@example.com", display_name="Test User")
    async with sessionmaker() as session:
        session.add(user)
        await session.commit()
    return user


async def _delete_user(sessionmaker: async_sessionmaker[AsyncSession], user: User) -> None:
    async with sessionmaker() as session:
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
        await session.commit()


@pytest.fixture
async def user(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[User]:
    """A committed user, removed afterwards along with everything it owns."""
    created = await _create_user(sessionmaker)
    yield created
    await _delete_user(sessionmaker, created)


@pytest.fixture
async def other_user(sessionmaker: async_sessionmaker[AsyncSession]) -> AsyncIterator[User]:
    """A second committed user, for proving data isolation."""
    created = await _create_user(sessionmaker)
    yield created
    await _delete_user(sessionmaker, created)


@pytest.fixture
def provider() -> MockOpenFinanceProvider:
    return MockOpenFinanceProvider(reference_date=REFERENCE_DATE)


@pytest.fixture
def api_client(
    settings: Settings,
    engine: AsyncEngine,
    provider: MockOpenFinanceProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """A client whose application talks to the test database.

    The app owns its own engine, created inside the test client's event loop, so the
    database URL is pinned through the environment rather than by sharing an engine
    across loops. The provider is swapped for the pinned-date sandbox.
    """
    monkeypatch.setenv("DATABASE_URL", str(settings.database_url))
    get_settings.cache_clear()
    app = create_app(settings)
    app.dependency_overrides[get_open_finance_provider] = lambda: provider
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()
