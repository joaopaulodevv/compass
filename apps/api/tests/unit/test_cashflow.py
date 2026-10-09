"""Cash-flow aggregation.

Pure functions over hand-written movements: no database, no fixtures loaded from disk,
so each number here is checked against one that was worked out by hand.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from compass_api.domain.analysis import Movement
from compass_api.domain.categories import ExpenseCategory
from compass_api.domain.open_finance import AccountType
from compass_api.services.cashflow import summarize

CHECKING = uuid.uuid4()
CARD = uuid.uuid4()
JUNE = date(2026, 6, 1)
JUNE_END = date(2026, 6, 30)


def movement(
    amount: str,
    category: ExpenseCategory,
    day: date = date(2026, 6, 10),
    account_id: uuid.UUID = CHECKING,
    account_type: AccountType = AccountType.CHECKING,
    description: str = "MOVEMENT",
    merchant_name: str | None = None,
) -> Movement:
    return Movement(
        id=uuid.uuid4(),
        account_id=account_id,
        account_type=account_type,
        booked_at=day,
        amount=Decimal(amount),
        category=category,
        description=description,
        merchant_name=merchant_name,
    )


def test_income_and_expenses_are_separated_by_sign() -> None:
    summary = summarize(
        [
            movement("8500.00", ExpenseCategory.INCOME),
            movement("-2400.00", ExpenseCategory.HOUSING),
            movement("-119.90", ExpenseCategory.UTILITIES),
        ],
        JUNE,
        JUNE_END,
    )

    assert summary.income == Decimal("8500.00")
    assert summary.expenses == Decimal("2519.90")
    assert summary.net == Decimal("5980.10")
    assert summary.movements_considered == 3
    assert summary.movements_excluded == 0


def test_credit_card_spending_is_not_counted_twice() -> None:
    """The decisive case.

    The bill payment leaves the checking account and the purchases hit the card. Both
    are real rows; only the purchases are spending. Counting both would overstate
    expenses by exactly the amount of the bill.
    """
    summary = summarize(
        [
            movement("8500.00", ExpenseCategory.INCOME),
            movement("-1684.30", ExpenseCategory.CREDIT_CARD_PAYMENT),
            movement(
                "-742.18",
                ExpenseCategory.GROCERIES,
                account_id=CARD,
                account_type=AccountType.CREDIT_CARD,
            ),
            movement(
                "-942.12",
                ExpenseCategory.DINING,
                account_id=CARD,
                account_type=AccountType.CREDIT_CARD,
            ),
        ],
        JUNE,
        JUNE_END,
    )

    assert summary.expenses == Decimal("1684.30")  # the purchases, not the bill
    assert summary.internal_movements == Decimal("1684.30")
    assert summary.movements_excluded == 1
    assert summary.net == Decimal("6815.70")


def test_transfers_to_own_savings_are_neither_income_nor_expense() -> None:
    """Both legs of the transfer are present, and both must drop out."""
    summary = summarize(
        [
            movement("-800.00", ExpenseCategory.INTERNAL_TRANSFER),
            movement(
                "800.00",
                ExpenseCategory.INTERNAL_TRANSFER,
                account_type=AccountType.SAVINGS,
            ),
        ],
        JUNE,
        JUNE_END,
    )

    assert summary.income == Decimal("0.00")
    assert summary.expenses == Decimal("0.00")
    assert summary.internal_movements == Decimal("1600.00")
    assert summary.movements_considered == 0
    assert summary.movements_excluded == 2


def test_an_unexplained_credit_still_counts_as_income() -> None:
    """A refund categorised as OTHER is money arriving; dropping it would understate."""
    summary = summarize([movement("412.60", ExpenseCategory.OTHER)], JUNE, JUNE_END)

    assert summary.income == Decimal("412.60")


def test_movements_outside_the_window_are_ignored() -> None:
    summary = summarize(
        [
            movement("-100.00", ExpenseCategory.GROCERIES, day=date(2026, 5, 31)),
            movement("-200.00", ExpenseCategory.GROCERIES, day=date(2026, 6, 1)),
            movement("-400.00", ExpenseCategory.GROCERIES, day=date(2026, 6, 30)),
            movement("-800.00", ExpenseCategory.GROCERIES, day=date(2026, 7, 1)),
        ],
        JUNE,
        JUNE_END,
    )

    assert summary.expenses == Decimal("600.00")


def test_monthly_series_marks_partial_months() -> None:
    """A window starting mid-month makes that month look cheap; it must say so."""
    summary = summarize(
        [
            movement("-100.00", ExpenseCategory.GROCERIES, day=date(2026, 5, 20)),
            movement("-200.00", ExpenseCategory.GROCERIES, day=date(2026, 6, 15)),
            movement("-300.00", ExpenseCategory.GROCERIES, day=date(2026, 7, 10)),
        ],
        date(2026, 5, 15),
        date(2026, 7, 20),
    )

    assert [month.month for month in summary.months] == [
        date(2026, 5, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
    ]
    assert [month.is_complete for month in summary.months] == [False, True, False]
    assert [month.month for month in summary.complete_months] == [date(2026, 6, 1)]


def test_months_without_movements_do_not_appear() -> None:
    """An absent month is unknown, not zero: zero-filling would drag down the median."""
    summary = summarize(
        [
            movement("-100.00", ExpenseCategory.GROCERIES, day=date(2026, 4, 10)),
            movement("-100.00", ExpenseCategory.GROCERIES, day=date(2026, 6, 10)),
        ],
        date(2026, 4, 1),
        JUNE_END,
    )

    assert [month.month for month in summary.months] == [date(2026, 4, 1), date(2026, 6, 1)]


def test_category_breakdown_is_ordered_and_shares_sum_to_one() -> None:
    summary = summarize(
        [
            movement("-600.00", ExpenseCategory.GROCERIES),
            movement("-300.00", ExpenseCategory.DINING),
            movement("-100.00", ExpenseCategory.TRANSPORT),
        ],
        JUNE,
        JUNE_END,
    )

    assert [total.category for total in summary.by_category] == [
        ExpenseCategory.GROCERIES,
        ExpenseCategory.DINING,
        ExpenseCategory.TRANSPORT,
    ]
    assert [total.share for total in summary.by_category] == [
        Decimal("0.6000"),
        Decimal("0.3000"),
        Decimal("0.1000"),
    ]
    assert sum(total.share for total in summary.by_category) == Decimal("1.0000")


def test_category_breakdown_covers_expenses_only() -> None:
    summary = summarize(
        [
            movement("8500.00", ExpenseCategory.INCOME),
            movement("-500.00", ExpenseCategory.GROCERIES),
            movement("-100.00", ExpenseCategory.CREDIT_CARD_PAYMENT),
        ],
        JUNE,
        JUNE_END,
    )

    assert [total.category for total in summary.by_category] == [ExpenseCategory.GROCERIES]


def test_empty_window_reports_zeros_not_an_error() -> None:
    summary = summarize([], JUNE, JUNE_END)

    assert summary.income == summary.expenses == summary.net == Decimal("0.00")
    assert summary.months == ()
    assert summary.by_category == ()


def test_sums_stay_exact_to_the_centavo() -> None:
    """The reason amounts are decimals: three ten-cent charges are thirty cents."""
    summary = summarize(
        [movement("-0.10", ExpenseCategory.OTHER) for _ in range(3)], JUNE, JUNE_END
    )

    assert summary.expenses == Decimal("0.30")


def test_inverted_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="since"):
        summarize([], JUNE_END, JUNE)
