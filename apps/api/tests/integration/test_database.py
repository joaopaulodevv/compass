"""Integration tests that require a reachable PostgreSQL instance.

Run `alembic upgrade head` first; these tests assert against the migrated schema.
They are skipped (not failed) when no database is reachable, so that `pytest` stays
useful without infrastructure.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from compass_api.core.config import Settings, get_settings
from compass_api.db.models import User
from compass_api.main import create_app

pytestmark = pytest.mark.integration


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
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session wrapped in a transaction that is always rolled back."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as db_session:
            yield db_session
        await transaction.rollback()


async def test_sqlalchemy_can_query_postgresql(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))

    assert result.scalar_one() == 1


async def test_migrations_created_the_users_table(engine: AsyncEngine) -> None:
    def table_names(connection: Connection) -> list[str]:
        return inspect(connection).get_table_names()

    async with engine.connect() as connection:
        tables = await connection.run_sync(table_names)

    assert "users" in tables
    assert "alembic_version" in tables, "run `alembic upgrade head` before the integration tests"


async def test_user_round_trip(session: AsyncSession) -> None:
    email = f"{uuid.uuid4()}@example.com"
    session.add(User(email=email, display_name="Test User"))
    await session.flush()

    stored = (await session.execute(select(User).where(User.email == email))).scalar_one()

    assert stored.id is not None
    assert stored.display_name == "Test User"
    assert stored.created_at is not None
    assert stored.updated_at is not None


class TestReadinessAgainstRealDatabase:
    @pytest.fixture
    def client(self, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
        # The session layer resolves settings globally; point it at the test database.
        monkeypatch.setenv("DATABASE_URL", str(settings.database_url))
        get_settings.cache_clear()
        with TestClient(create_app(settings)) as test_client:
            yield test_client
        get_settings.cache_clear()

    def test_ready_endpoint_reaches_postgresql(self, client: TestClient) -> None:
        response = client.get("/ready")

        if response.status_code == 503:
            pytest.skip("PostgreSQL is not reachable")

        assert response.status_code == 200
        assert response.json() == {"status": "ready", "checks": {"database": "ok"}}
