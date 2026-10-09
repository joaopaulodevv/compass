"""Money handling rules, in one place.

Monetary amounts are `Decimal`, never `float`: binary floating point cannot represent
R$ 0.10 exactly, and rounding drift in a financial ledger is a correctness bug, not a
display issue.

Amounts are **signed**: a negative amount is money leaving the account (a purchase, a
transfer out, a bill), a positive amount is money arriving (salary, interest, refund).
Keeping one signed column - rather than a magnitude plus a direction flag - means
summing a window is addition, with no branch to get wrong.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Final

#: Database precision for monetary columns: 16 integer digits, 2 decimal places.
MONEY_PRECISION: Final = 18
MONEY_SCALE: Final = 2

#: ISO-4217 code length. Compass is BRL-first but stores the currency per account.
CURRENCY_CODE_LENGTH: Final = 3


class Direction(StrEnum):
    """Which way the money moved, derived from the sign of an amount."""

    INFLOW = "inflow"
    OUTFLOW = "outflow"

    @classmethod
    def of(cls, amount: Decimal) -> Direction:
        return cls.OUTFLOW if amount < 0 else cls.INFLOW
