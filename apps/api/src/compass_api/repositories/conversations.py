"""Reads and writes for `conversations` and `conversation_messages`."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.db.models import Conversation, ConversationMessage


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation: Conversation) -> Conversation:
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Conversation]:
        """Most recently updated first - the order a chat list is read in."""
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        return (await self._session.execute(statement)).scalars().all()

    async def get_for_user(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Conversation | None:
        statement = select(Conversation).where(
            Conversation.user_id == user_id, Conversation.id == conversation_id
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add_message(self, message: ConversationMessage) -> ConversationMessage:
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_messages(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Sequence[ConversationMessage]:
        """The thread in order, scoped by owner."""
        statement = (
            select(ConversationMessage)
            .where(
                ConversationMessage.user_id == user_id,
                ConversationMessage.conversation_id == conversation_id,
            )
            .order_by(ConversationMessage.created_at, ConversationMessage.id)
        )
        return (await self._session.execute(statement)).scalars().all()
