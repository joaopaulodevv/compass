"""The conversational endpoint.

A turn is synchronous: the request returns when the agent has an answer. Streaming is a
frontend concern and a later phase; the tool-calling loop underneath it would not change.

The assistant's message carries the tool calls that produced it. ADR-0005 promises every
number traces back to a tool call, and this is where a reader can check that promise.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from compass_api.agent.llm.base import Role
from compass_api.agent.service import ConversationService, UnknownUserError
from compass_api.api.deps import CurrentUserId, LLMProviderDep, SessionDep
from compass_api.db.models import Conversation

router = APIRouter(prefix="/conversations", tags=["assistant"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "No such conversation for this user"}
}
UNAVAILABLE: dict[int | str, dict[str, Any]] = {
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "The assistant is not configured"}
}


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: Role
    content: str
    #: Present on an assistant turn that used tools: the audit trail for its numbers.
    tool_calls: list[dict[str, Any]] | None
    model: str | None
    created_at: datetime


class MessageListResponse(BaseModel):
    items: list[MessageResponse]


class CreateConversationRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class ExchangeResponse(BaseModel):
    """The user's turn and the assistant's reply, plus what the turn cost."""

    conversation_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    prompt_tokens: int
    completion_tokens: int


async def _require_conversation(
    service: ConversationService, user_id: UUID, conversation_id: UUID
) -> Conversation:
    conversation = await service.get(user_id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Start a conversation",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such user"}, **UNAVAILABLE},
)
async def create_conversation(
    request: CreateConversationRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    provider: LLMProviderDep,
) -> ConversationResponse:
    try:
        conversation = await ConversationService(session, provider).create(user_id, request.title)
    except UnknownUserError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        ) from error
    return ConversationResponse.model_validate(conversation)


@router.get("", summary="List the user's conversations", responses=UNAVAILABLE)
async def list_conversations(
    user_id: CurrentUserId, session: SessionDep, provider: LLMProviderDep
) -> ConversationListResponse:
    conversations = await ConversationService(session, provider).list(user_id)
    return ConversationListResponse(
        items=[ConversationResponse.model_validate(item) for item in conversations]
    )


@router.get(
    "/{conversation_id}/messages",
    summary="Read a conversation",
    responses={**NOT_FOUND, **UNAVAILABLE},
)
async def list_messages(
    conversation_id: UUID,
    user_id: CurrentUserId,
    session: SessionDep,
    provider: LLMProviderDep,
) -> MessageListResponse:
    service = ConversationService(session, provider)
    await _require_conversation(service, user_id, conversation_id)
    messages = await service.messages(user_id, conversation_id)
    return MessageListResponse(
        items=[MessageResponse.model_validate(message) for message in messages]
    )


@router.post(
    "/{conversation_id}/messages",
    summary="Send a message and get the assistant's answer",
    responses={**NOT_FOUND, **UNAVAILABLE},
)
async def send_message(
    conversation_id: UUID,
    request: SendMessageRequest,
    user_id: CurrentUserId,
    session: SessionDep,
    provider: LLMProviderDep,
) -> ExchangeResponse:
    service = ConversationService(session, provider)
    conversation = await _require_conversation(service, user_id, conversation_id)
    exchange = await service.send(user_id, conversation, request.content)
    return ExchangeResponse(
        conversation_id=conversation.id,
        user_message=MessageResponse.model_validate(exchange.user_message),
        assistant_message=MessageResponse.model_validate(exchange.assistant_message),
        prompt_tokens=exchange.turn.usage.prompt_tokens,
        completion_tokens=exchange.turn.usage.completion_tokens,
    )
