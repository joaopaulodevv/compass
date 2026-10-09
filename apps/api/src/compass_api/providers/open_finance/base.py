"""The contract Compass owns.

No provider has been chosen (Pluggy, Belvo and others are candidates). The application
therefore depends on this protocol, never on a vendor SDK: an adapter translates one
vendor's payloads into `compass_api.domain.open_finance` snapshots and nothing else in
the system changes when the vendor does.

A `Protocol` rather than an abstract base class: an adapter satisfies it structurally,
so a test double is a plain class with the right methods and no import of ours.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable
from uuid import UUID

from compass_api.domain.open_finance import (
    AccountSnapshot,
    InstitutionSnapshot,
    TransactionSnapshot,
)


@runtime_checkable
class OpenFinanceProvider(Protocol):
    """Read-only access to one user's financial data at an Open Finance provider."""

    @property
    def name(self) -> str:
        """Stable identifier persisted alongside ingested rows (e.g. `"mock"`).

        Stored per row so that data from different providers can coexist, and so that a
        provider's records can be re-synced or retired without touching the others.
        """
        ...

    async def get_institutions(self, user_id: UUID) -> Sequence[InstitutionSnapshot]:
        """Institutions the user has connected."""
        ...

    async def get_accounts(self, user_id: UUID) -> Sequence[AccountSnapshot]:
        """Accounts the user holds, with the balance the provider currently reports."""
        ...

    async def get_transactions(
        self, user_id: UUID, since: date, until: date
    ) -> Sequence[TransactionSnapshot]:
        """Transactions booked within the inclusive window `[since, until]`."""
        ...
