"""The signed-amount convention."""

from __future__ import annotations

from decimal import Decimal

import pytest

from compass_api.domain.money import Direction


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (Decimal("-0.01"), Direction.OUTFLOW),
        (Decimal("-2400.00"), Direction.OUTFLOW),
        (Decimal("8500.00"), Direction.INFLOW),
        (Decimal("0.01"), Direction.INFLOW),
        # A zero-value movement (a reversal netting out, a fee waived) is not an outflow.
        (Decimal("0.00"), Direction.INFLOW),
    ],
)
def test_direction_follows_the_sign(amount: Decimal, expected: Direction) -> None:
    assert Direction.of(amount) is expected
