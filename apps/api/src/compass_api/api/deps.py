"""Shared FastAPI dependencies.

The composition root for request-scoped collaborators: the database session, the caller's
identity, and the Open Finance provider. Routes declare what they need and never
construct it, which is what lets tests swap any of it with
`app.dependency_overrides`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

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
