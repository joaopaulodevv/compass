"""The development seed command.

It leaves the demo user behind on purpose - that is what it is for, and running it twice
must be safe.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from compass_api.core.config import Settings, get_settings
from compass_api.db.session import dispose_engine
from compass_api.seed import DEMO_EMAIL, DEMO_USER_ID, main, seed_demo_user

pytestmark = pytest.mark.integration


@pytest.fixture
async def pinned_settings(
    settings: Settings,
    engine: AsyncEngine,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Point the seed's own engine at the test database, with no demo user present.

    Removing it first means the test covers the insert and the no-op alike, whether or
    not a developer has already run the command on this database.
    """
    async with sessionmaker() as session:
        await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": DEMO_USER_ID})
        await session.commit()
    monkeypatch.setenv("DATABASE_URL", str(settings.database_url))
    get_settings.cache_clear()


async def test_seeding_twice_yields_the_same_user(pinned_settings: None) -> None:
    try:
        first = await seed_demo_user()
        second = await seed_demo_user()
    finally:
        await dispose_engine()
        get_settings.cache_clear()

    assert first.id == second.id == DEMO_USER_ID
    assert first.email == DEMO_EMAIL


def test_cli_prints_the_header_value_to_use(
    pinned_settings: None, capsys: pytest.CaptureFixture[str]
) -> None:
    try:
        main()
    finally:
        get_settings.cache_clear()

    output = capsys.readouterr().out
    assert str(DEMO_USER_ID) in output
    assert "X-User-Id" in output
