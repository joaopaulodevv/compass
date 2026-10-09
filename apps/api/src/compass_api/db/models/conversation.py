"""The `conversations` and `conversation_messages` tables."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from compass_api.agent.llm.base import Role
from compass_api.db.base import Base, TimestampMixin

#: Roles that are persisted. System prompts are rebuilt each turn - storing them would
#: freeze a prompt into history - and tool results are kept as metadata on the assistant
#: message that caused them rather than as turns of their own.
STORED_ROLES = (Role.USER, Role.ASSISTANT)


class Conversation(Base, TimestampMixin):
    """A thread of messages between one user and the assistant."""

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200))


class ConversationMessage(Base, TimestampMixin):
    """One turn. Assistant turns record which tools produced their numbers.

    That record is what makes an answer auditable after the fact: ADR-0005 promises every
    figure traces back to a tool call, and this column is where the trace lives.
    """

    __tablename__ = "conversation_messages"
    __table_args__ = (
        Index("ix_conversation_messages_conversation_id", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    #: Denormalised from the conversation so every read filters on the owner directly.
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Role] = mapped_column(
        Enum(
            Role,
            native_enum=False,
            create_constraint=True,
            length=16,
            name="message_role",
            validate_strings=True,
        )
    )
    content: Mapped[str] = mapped_column(String(16000))
    #: `[{"name": "get_cashflow", "arguments": {...}}, ...]` for an assistant turn.
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, default=None)
    #: Which model produced this turn, so an answer can be read against its author.
    model: Mapped[str | None] = mapped_column(String(64), default=None)
