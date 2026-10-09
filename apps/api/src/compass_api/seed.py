"""Create the local demo user.

Authentication does not exist yet, so there is no sign-up path - but every request needs
a `user_id`, and the foreign keys mean one has to exist before anything can be ingested.
This seeds exactly one, idempotently, with a fixed id so the development docs can show a
header value that works on any machine.

    uv run --directory apps/api python -m compass_api.seed

It is development scaffolding, not a fixture factory: tests create their own users.
"""

from __future__ import annotations

import asyncio
import uuid

from compass_api.core.config import get_settings
from compass_api.core.logging import configure_logging
from compass_api.db.models import User
from compass_api.db.session import dispose_engine, get_sessionmaker
from compass_api.repositories.users import UserRepository

DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_EMAIL = "demo@compass.local"
DEMO_DISPLAY_NAME = "Demo User"


async def seed_demo_user() -> User:
    """Insert the demo user if it is not already there, and return it."""
    async with get_sessionmaker()() as session:
        repository = UserRepository(session)
        existing = await repository.get(DEMO_USER_ID)
        if existing is not None:
            return existing

        user = await repository.add(
            User(id=DEMO_USER_ID, email=DEMO_EMAIL, display_name=DEMO_DISPLAY_NAME)
        )
        await session.commit()
        return user


def main() -> None:
    configure_logging(get_settings())

    async def run() -> User:
        try:
            return await seed_demo_user()
        finally:
            await dispose_engine()

    user = asyncio.run(run())
    print(f"demo user ready: {user.id} <{user.email}>")
    print(f'try: curl -H "X-User-Id: {user.id}" localhost:8000/accounts')


if __name__ == "__main__":
    main()
