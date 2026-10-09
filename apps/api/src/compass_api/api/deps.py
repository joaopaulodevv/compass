"""Shared FastAPI dependencies.

The composition root for request-scoped collaborators: the database session, the caller's
identity, and the Open Finance provider. Routes declare what they need and never
construct it, which is what lets tests swap any of it with
`app.dependency_overrides`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.agent.llm import LLMProvider
from compass_api.agent.llm.openai import OpenAIProvider
from compass_api.core.config import Settings, get_settings
from compass_api.db.session import get_session
from compass_api.providers.open_finance import MockOpenFinanceProvider, OpenFinanceProvider

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Header carrying the acting user until authentication exists.
USER_ID_HEADER = "X-User-Id"


async def get_current_user_id(
    user_id: Annotated[
        UUID,
        Header(
            alias=USER_ID_HEADER,
            description=(
                "Identifies the acting user. A temporary stand-in for authentication: "
                "once it exists this value comes from the verified token instead, and "
                "the header disappears. Every query is already scoped by it."
            ),
        ),
    ],
) -> UUID:
    """Resolve the acting user from the request.

    This trusts the caller, which is why it is development-only and why the roadmap puts
    authentication before any deployment. The value it returns is the isolation key used
    by every repository call, so swapping its source later changes nothing downstream.
    """
    return user_id


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]


def get_open_finance_provider() -> OpenFinanceProvider:
    """The provider implementation this deployment ingests from.

    The sandbox mock, always, in this phase - no vendor has been chosen and no real
    credentials exist. When one is added, this is the single place that selects it
    (by configuration), and nothing else in the application changes.
    """
    return MockOpenFinanceProvider()


OpenFinanceProviderDep = Annotated[OpenFinanceProvider, Depends(get_open_finance_provider)]


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_llm_provider(settings: SettingsDep) -> LLMProvider:
    """The model the conversational endpoints talk to.

    Absent a key, this raises 503 rather than letting the application fail to start: the
    financial API is useful on its own, and a missing future credential must never be
    what stops it (see `core.config`).

    This is the only place that chooses an implementation. Adding a second provider is a
    branch here and an adapter beside `agent/llm/openai.py` - nothing else changes.
    """
    if settings.openai_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The assistant is not configured: OPENAI_API_KEY is not set.",
        )
    return OpenAIProvider(
        api_key=settings.openai_api_key.get_secret_value(), model=settings.openai_model
    )


LLMProviderDep = Annotated[LLMProvider, Depends(get_llm_provider)]
