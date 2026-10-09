"""The database stack itself: connectivity, migrated schema, ORM round trip."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Connection, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from compass_api.db.models import User

pytestmark = pytest.mark.integration


async def test_sqlalchemy_can_query_postgresql(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))

    assert result.scalar_one() == 1


async def test_migrations_created_every_table(engine: AsyncEngine) -> None:
    def table_names(connection: Connection) -> list[str]:
        return inspect(connection).get_table_names()

    async with engine.connect() as connection:
        tables = await connection.run_sync(table_names)

    assert {"users", "financial_institutions", "accounts", "transactions"} <= set(tables)
    assert "alembic_version" in tables, "run `alembic upgrade head` before the integration tests"


async def test_user_round_trip(tx_session: AsyncSession) -> None:
    email = f"{uuid.uuid4()}@example.com"
    tx_session.add(User(email=email, display_name="Test User"))
    await tx_session.flush()

    stored = (await tx_session.execute(select(User).where(User.email == email))).scalar_one()

    assert stored.id is not None
    assert stored.display_name == "Test User"
    assert stored.created_at is not None
    assert stored.updated_at is not None
