"""Sandbox provider backed by a committed fixture.

Development and tests run against this. It returns the same realistic six-month history
for every user, which is enough to exercise ingestion now and the cash-flow,
recurring-expense and saving-capacity calculations in later phases.

Transaction dates live in the fixture as a month offset plus a day, resolved against a
reference date (today, unless a caller pins it). The data therefore always sits in the
recent past without anyone rewriting the file, and a test that pins the reference date
gets byte-identical results.

Real financial credentials are never involved, and no network call is made.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from compass_api.domain.dates import add_months, with_day
from compass_api.domain.open_finance import (
    AccountSnapshot,
    InstitutionSnapshot,
    TransactionSnapshot,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sandbox.json"

PROVIDER_NAME = "mock"


class _FixtureTransaction(BaseModel):
    """A transaction as stored in the fixture, with a relative date."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    external_id: str
    account_external_id: str
    month_offset: int = Field(le=0)
    day: int = Field(ge=1, le=31)
    amount: str
    currency: str
    description: str
    merchant_name: str | None = None
    provider_category: str | None = None


class _Fixture(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    institutions: tuple[InstitutionSnapshot, ...]
    accounts: tuple[AccountSnapshot, ...]
    transactions: tuple[_FixtureTransaction, ...]


@lru_cache
def _load_fixture(path: Path) -> _Fixture:
    """Read and validate the fixture once per path."""
    return _Fixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _shift_month(reference: date, month_offset: int, day: int) -> date:
    """Resolve a (month offset, day) pair into a real date.

    The day is clamped to the length of the target month, so a fixture entry on day 31
    lands on the last day of February rather than failing.
    """
    return with_day(add_months(reference.replace(day=1), month_offset), day)


class MockOpenFinanceProvider:
    """`OpenFinanceProvider` implementation over the committed sandbox fixture."""

    def __init__(
        self, reference_date: date | None = None, fixture_path: Path | None = None
    ) -> None:
        self._reference_date = reference_date or date.today()
        self._fixture = _load_fixture(fixture_path or FIXTURE_PATH)

    @property
    def name(self) -> str:
        return PROVIDER_NAME

    @property
    def reference_date(self) -> date:
        """The date month offsets are resolved against."""
        return self._reference_date

    async def get_institutions(self, user_id: UUID) -> Sequence[InstitutionSnapshot]:
        """The sandbox exposes the same institutions to every user."""
        return self._fixture.institutions

    async def get_accounts(self, user_id: UUID) -> Sequence[AccountSnapshot]:
        """The sandbox exposes the same accounts to every user."""
        return self._fixture.accounts

    async def get_transactions(
        self, user_id: UUID, since: date, until: date
    ) -> Sequence[TransactionSnapshot]:
        """Transactions booked in `[since, until]`, oldest first."""
        if since > until:
            raise ValueError("since must not be later than until")

        resolved = (
            TransactionSnapshot(
                external_id=entry.external_id,
                account_external_id=entry.account_external_id,
                booked_at=_shift_month(self._reference_date, entry.month_offset, entry.day),
                # pydantic parses the exact decimal string; no float ever appears.
                amount=entry.amount,
                currency=entry.currency,
                description=entry.description,
                merchant_name=entry.merchant_name,
                provider_category=entry.provider_category,
            )
            for entry in self._fixture.transactions
        )
        in_window = [snapshot for snapshot in resolved if since <= snapshot.booked_at <= until]
        return sorted(in_window, key=lambda snapshot: (snapshot.booked_at, snapshot.external_id))
