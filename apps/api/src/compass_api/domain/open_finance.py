"""Provider-neutral view of financial data.

These are the only shapes the application accepts from an Open Finance provider. A
provider adapter translates its vendor payload into them, so nothing downstream - the
ingestion service, the repositories, the future financial engine - knows which vendor
the data came from, or whether it came from a vendor at all.

They are snapshots: what the provider reported at a point in time, not Compass's own
records. Persisted entities live in `compass_api.db.models`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from compass_api.domain.money import CURRENCY_CODE_LENGTH


class AccountType(StrEnum):
    """The account kinds Compass reasons about.

    Deliberately coarse: the financial engine cares whether money is liquid, invested or
    borrowed, not about a provider's product taxonomy.
    """

    CHECKING = "CHECKING"
    SAVINGS = "SAVINGS"
    CREDIT_CARD = "CREDIT_CARD"
    INVESTMENT = "INVESTMENT"


class _Snapshot(BaseModel):
    """Immutable, strictly validated provider payload."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)


class InstitutionSnapshot(_Snapshot):
    """A financial institution as the provider identifies it."""

    external_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class AccountSnapshot(_Snapshot):
    """An account held by the user at an institution."""

    external_id: str = Field(min_length=1, max_length=128)
    institution_external_id: str = Field(min_length=1, max_length=128)
    type: AccountType
    name: str = Field(min_length=1, max_length=255)
    currency: str = Field(min_length=CURRENCY_CODE_LENGTH, max_length=CURRENCY_CODE_LENGTH)
    current_balance: Decimal


class TransactionSnapshot(_Snapshot):
    """A single movement on an account.

    `amount` is signed (see `compass_api.domain.money`). `external_id` is the provider's
    own identifier and is what makes ingestion idempotent - re-reading the same window
    must not create a second row.
    """

    external_id: str = Field(min_length=1, max_length=128)
    account_external_id: str = Field(min_length=1, max_length=128)
    booked_at: date
    amount: Decimal
    currency: str = Field(min_length=CURRENCY_CODE_LENGTH, max_length=CURRENCY_CODE_LENGTH)
    description: str = Field(min_length=1, max_length=512)
    merchant_name: str | None = Field(default=None, max_length=255)
    provider_category: str | None = Field(default=None, max_length=128)
