"""Conversations: persistence around a turn of the agent.

The service owns what the agent should not: who the user is, what was said before, and
what to keep afterwards. The agent itself is handed a list of messages and returns an
answer.

History is replayed as plain user and assistant turns. The system prompt is rebuilt every
time rather than stored, so improving it improves every future answer instead of leaving
old threads frozen on an old prompt. Tool results are not replayed either - they were
true when fetched, and a figure from last week presented as current would be worse than
fetching it again.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.agent.graph import AgentTurn, FinancialAgent
from compass_api.agent.llm.base import LLMMessage, LLMProvider, Role
from compass_api.agent.prompt import SYSTEM_PROMPT
from compass_api.db.models import Conversation, ConversationMessage
from compass_api.repositories.conversations import ConversationRepository
from compass_api.repositories.users import UserRepository

logger = logging.getLogger(__name__)

#: How many stored turns are replayed to the model. Enough for a coherent conversation,
#: bounded so a long thread cannot grow the prompt without limit.
HISTORY_LIMIT = 20

DEFAULT_TITLE = "New conversation"
TITLE_LENGTH = 60


class UnknownUserError(LookupError):
    """The user does not exist, so there is nothing to attach a conversation to."""

    def __init__(self, user_id: uuid.UUID) -> None:
        super().__init__(str(user_id))
        self.user_id = user_id


@dataclass(frozen=True, slots=True)
class Exchange:
    """What one `POST` of a message produced."""

    user_message: ConversationMessage
    assistant_message: ConversationMessage
    turn: AgentTurn


class ConversationService:
    def __init__(self, session: AsyncSession, provider: LLMProvider) -> None:
        self._session = session
        self._conversations = ConversationRepository(session)
        self._users = UserRepository(session)
        self._agent = FinancialAgent(provider)

    async def create(self, user_id: uuid.UUID, title: str | None = None) -> Conversation:
        """Start a thread.

        Raises:
            UnknownUserError: if no such user exists.
        """
        if await self._users.get(user_id) is None:
            raise UnknownUserError(user_id)

        conversation = await self._conversations.add(
            Conversation(user_id=user_id, title=title or DEFAULT_TITLE)
        )
        await self._session.commit()
        return conversation

    async def list(self, user_id: uuid.UUID) -> Sequence[Conversation]:
        return await self._conversations.list_for_user(user_id)

    async def get(self, user_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation | None:
        return await self._conversations.get_for_user(user_id, conversation_id)

    async def messages(
        self, user_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Sequence[ConversationMessage]:
        return await self._conversations.list_messages(user_id, conversation_id)

    async def send(self, user_id: uuid.UUID, conversation: Conversation, text: str) -> Exchange:
        """Record the user's message, answer it, and record the answer."""
        history = await self._conversations.list_messages(user_id, conversation.id)

        user_message = await self._conversations.add_message(
            ConversationMessage(
                conversation_id=conversation.id,
                user_id=user_id,
                role=Role.USER,
                content=text,
            )
        )
        # The first thing a user says is the best title available, and better than
        # asking them for one.
        if conversation.title == DEFAULT_TITLE:
            conversation.title = text[:TITLE_LENGTH]
        await self._session.commit()

        turn = await self._agent.run(_as_llm_messages(history, text), user_id)

        assistant_message = await self._conversations.add_message(
            ConversationMessage(
                conversation_id=conversation.id,
                user_id=user_id,
                role=Role.ASSISTANT,
                content=turn.answer,
                tool_calls=list(turn.tool_calls) or None,
                model=turn.model,
            )
        )
        await self._session.commit()

        logger.info(
            "conversation turn completed",
            extra={
                "user_id": str(user_id),
                "conversation_id": str(conversation.id),
                "model": turn.model,
                "tool_calls": len(turn.tool_calls),
                "prompt_tokens": turn.usage.prompt_tokens,
                "completion_tokens": turn.usage.completion_tokens,
            },
        )
        return Exchange(user_message=user_message, assistant_message=assistant_message, turn=turn)


def _as_llm_messages(history: Sequence[ConversationMessage], new_message: str) -> list[LLMMessage]:
    recent = history[-HISTORY_LIMIT:]
    messages = [LLMMessage.system(SYSTEM_PROMPT)]
    for message in recent:
        if message.role is Role.USER:
            messages.append(LLMMessage.user(message.content))
        elif message.role is Role.ASSISTANT:
            messages.append(LLMMessage.assistant(message.content))
    messages.append(LLMMessage.user(new_message))
    return messages
