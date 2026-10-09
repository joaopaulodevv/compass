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

from collections.abc import Sequence
from decimal import ROUND_HALF_UP, Decimal
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


#: Every monetary result is rounded to this before leaving the engine, so a figure the
#: user sees is a figure that can be stored and compared without surprise.
CENT = Decimal("0.01")


def quantize_money(value: Decimal) -> Decimal:
    """Round to centavos, half away from zero.

    Sums of stored amounts are already exact; this matters for derived figures such as a
    mean or a median of an even number of values.
    """
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def median_money(values: Sequence[Decimal]) -> Decimal:
    """Median of monetary values, rounded to centavos.

    The median rather than the mean wherever one unusual month must not move the answer:
    a bonus or an annual insurance premium should not change what the user is told they
    can save every month.

    Raises:
        ValueError: if there are no values - an empty median has no meaningful answer,
            and returning zero would read as "can save nothing".
    """
    if not values:
        raise ValueError("median of no values is undefined")

    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return quantize_money(ordered[middle])
    return quantize_money((ordered[middle - 1] + ordered[middle]) / 2)


def mean_money(values: Sequence[Decimal]) -> Decimal:
    """Arithmetic mean, rounded to centavos."""
    if not values:
        raise ValueError("mean of no values is undefined")
    return quantize_money(sum(values, start=Decimal(0)) / len(values))
