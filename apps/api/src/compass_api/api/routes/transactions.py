"""Read access to the user's transactions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict

from compass_api.api.deps import CurrentUserId, SessionDep
from compass_api.db.models import Transaction
from compass_api.domain.categories import ExpenseCategory
from compass_api.domain.money import Direction
from compass_api.repositories.transactions import TransactionRepository

router = APIRouter(prefix="/transactions", tags=["transactions"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


class TransactionResponse(BaseModel):
    """A transaction as the API exposes it.

    `amount` is signed (negative is an outflow) and serialised as a JSON string to keep
    the decimal exact. `direction` is derived from the sign and included so clients do
    not each reimplement the comparison.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    booked_at: date
    amount: Decimal
    currency: str
    direction: Direction
    description: str
    merchant_name: str | None
    #: The provider's own label, kept verbatim.
    provider_category: str | None
    #: Compass's category, assigned by the deterministic rule engine, and the rule that
    #: produced it - so a surprising label can be traced to its cause.
    category: ExpenseCategory
    category_rule: str | None

    @classmethod
    def of(cls, transaction: Transaction) -> TransactionResponse:
        return cls.model_validate(transaction)


class TransactionPage(BaseModel):
    items: list[TransactionResponse]
    total: int
    limit: int
    offset: int


@router.get("", summary="List the user's transactions, most recent first")
async def list_transactions(
    user_id: CurrentUserId,
    session: SessionDep,
    account_id: Annotated[UUID | None, Query(description="Restrict to one account")] = None,
    since: Annotated[date | None, Query(description="Booked on or after this date")] = None,
    until: Annotated[date | None, Query(description="Booked on or before this date")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    repository = TransactionRepository(session)
    transactions = await repository.list_for_user(
        user_id, account_id=account_id, since=since, until=until, limit=limit, offset=offset
    )
    total = await repository.count_for_user(
        user_id, account_id=account_id, since=since, until=until
    )
    return TransactionPage(
        items=[TransactionResponse.of(transaction) for transaction in transactions],
        total=total,
        limit=limit,
        offset=offset,
    )
