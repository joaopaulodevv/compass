"""Repository guard clauses.

These paths deliberately never touch the database, which is why they can be tested
without one: passing a sentinel in place of a session proves no query is attempted.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from compass_api.domain.open_finance import AccountSnapshot, AccountType, TransactionSnapshot
from compass_api.repositories.accounts import AccountRepository, UnknownInstitutionError
from compass_api.repositories.institutions import InstitutionRepository
from compass_api.repositories.transactions import TransactionRepository, UnknownAccountError

NOW = datetime(2026, 6, 15, tzinfo=UTC)
USER_ID = uuid.uuid4()

#: Using a session the code must never call: any query would raise AttributeError.
NO_SESSION = cast(AsyncSession, object())

ACCOUNT = AccountSnapshot(
    external_id="acc-1",
    institution_external_id="bank",
    type=AccountType.CHECKING,
    name="Conta",
    currency="BRL",
    current_balance=Decimal("10.00"),
)
TRANSACTION = TransactionSnapshot(
    external_id="txn-1",
    account_external_id="acc-1",
    booked_at=NOW.date(),
    amount=Decimal("-10.00"),
    currency="BRL",
    description="COMPRA",
)


async def test_empty_institution_batch_is_a_no_op() -> None:
    assert await InstitutionRepository(NO_SESSION).upsert_many("mock", []) == {}


async def test_empty_account_batch_is_a_no_op() -> None:
    result = await AccountRepository(NO_SESSION).upsert_many(
        user_id=USER_ID, provider="mock", snapshots=[], institution_ids={}, synced_at=NOW
    )

    assert result == {}


async def test_empty_transaction_batch_is_a_no_op() -> None:
    written = await TransactionRepository(NO_SESSION).upsert_many(
        user_id=USER_ID,
        provider="mock",
        snapshots=[],
        account_ids={},
        categorizations={},
        synced_at=NOW,
    )

    assert written == 0


async def test_account_referencing_an_unknown_institution_fails_loudly() -> None:
    """Silently dropping it would leave the user with a partial, plausible-looking sync."""
    with pytest.raises(UnknownInstitutionError, match="bank"):
        await AccountRepository(NO_SESSION).upsert_many(
            user_id=USER_ID,
            provider="mock",
            snapshots=[ACCOUNT],
            institution_ids={},
            synced_at=NOW,
        )


async def test_transaction_referencing_an_unknown_account_fails_loudly() -> None:
    with pytest.raises(UnknownAccountError, match="acc-1"):
        await TransactionRepository(NO_SESSION).upsert_many(
            user_id=USER_ID,
            provider="mock",
            snapshots=[TRANSACTION],
            account_ids={},
            categorizations={},
            synced_at=NOW,
        )
