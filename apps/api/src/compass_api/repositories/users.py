"""Reads and writes for `users`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user
