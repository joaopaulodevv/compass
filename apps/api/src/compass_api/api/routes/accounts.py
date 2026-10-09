"""Read access to the user's accounts.

Every query is scoped by the acting user, so an id belonging to someone else reads as
"not found" rather than as somebody else's balance.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from compass_api.api.deps import CurrentUserId, SessionDep
from compass_api.db.models import Account
from compass_api.domain.open_finance import AccountType
from compass_api.repositories.accounts import AccountRepository

router = APIRouter(prefix="/accounts", tags=["accounts"])


class InstitutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str


class AccountResponse(BaseModel):
    """An account as the API exposes it.

    `current_balance` is serialised as a JSON string: it is a `Decimal`, and rendering it
    as a JSON number would hand clients a float to round badly.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    institution: InstitutionResponse
    type: AccountType
    name: str
    currency: str
    current_balance: Decimal
    synced_at: datetime

    @classmethod
    def of(cls, account: Account) -> AccountResponse:
        return cls.model_validate(account)


class AccountListResponse(BaseModel):
    items: list[AccountResponse]


@router.get("", summary="List the user's accounts")
async def list_accounts(user_id: CurrentUserId, session: SessionDep) -> AccountListResponse:
    accounts = await AccountRepository(session).list_for_user(user_id)
    return AccountListResponse(items=[AccountResponse.of(account) for account in accounts])


@router.get(
    "/{account_id}",
    summary="Get one account",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No such account for this user"}},
)
async def get_account(
    account_id: UUID, user_id: CurrentUserId, session: SessionDep
) -> AccountResponse:
    account = await AccountRepository(session).get_for_user(user_id, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return AccountResponse.of(account)
