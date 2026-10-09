"""Recurring expense detection."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from compass_api.domain.analysis import Movement
from compass_api.domain.categories import ExpenseCategory
from compass_api.domain.open_finance import AccountType
from compass_api.services.recurring import detect

CARD = uuid.uuid4()
OTHER_CARD = uuid.uuid4()
START = date(2026, 1, 5)


def charge(
    amount: str,
    day: date,
    *,
    merchant: str | None = "Netflix",
    description: str = "NETFLIX.COM",
    category: ExpenseCategory = ExpenseCategory.SUBSCRIPTIONS,
    account_id: uuid.UUID = CARD,
) -> Movement:
    return Movement(
        id=uuid.uuid4(),
        account_id=account_id,
        account_type=AccountType.CREDIT_CARD,
        booked_at=day,
        amount=Decimal(amount),
        category=category,
        description=description,
        merchant_name=merchant,
    )


def monthly(amounts: list[str], *, start: date = START, **kwargs: object) -> list[Movement]:
    return [
        charge(amount, start + timedelta(days=30 * index), **kwargs)  # type: ignore[arg-type]
        for index, amount in enumerate(amounts)
    ]


def test_a_fixed_monthly_subscription_is_detected() -> None:
    found = detect(monthly(["-55.90", "-55.90", "-55.90", "-55.90"]))

    assert len(found) == 1
    subscription = found[0]
    assert subscription.label == "Netflix"
    assert subscription.category is ExpenseCategory.SUBSCRIPTIONS
    assert subscription.occurrences == 4
    assert subscription.median_amount == Decimal("55.90")
    assert subscription.average_interval_days == 30
    assert subscription.first_seen == START
    assert subscription.last_seen == START + timedelta(days=90)
    assert subscription.expected_next == subscription.last_seen + timedelta(days=30)


def test_a_bill_that_drifts_with_usage_still_counts() -> None:
    """Electricity moves with the season; it is no less a monthly commitment."""
    found = detect(
        monthly(
            ["-175.20", "-212.45", "-188.90", "-241.65"],
            merchant="Enel",
            description="ENERGIA ELETRICA",
            category=ExpenseCategory.UTILITIES,
        )
    )

    assert len(found) == 1
    assert found[0].median_amount == Decimal("200.68")


def test_two_occurrences_are_not_yet_a_pattern() -> None:
    assert detect(monthly(["-55.90", "-55.90"])) == ()


def test_wildly_varying_amounts_are_not_one_recurring_charge() -> None:
    """Visiting the same merchant monthly for unpredictable sums is not a commitment."""
    assert detect(monthly(["-50.00", "-400.00", "-120.00", "-980.00"])) == ()


def test_weekly_charges_are_not_monthly_recurrence() -> None:
    weekly = [charge("-55.90", START + timedelta(days=7 * index)) for index in range(6)]

    assert detect(weekly) == ()


def test_annual_charges_are_not_monthly_recurrence() -> None:
    annual = [charge("-299.00", START + timedelta(days=365 * index)) for index in range(3)]

    assert detect(annual) == ()


def test_the_same_merchant_on_two_cards_is_two_commitments() -> None:
    found = detect(
        monthly(["-55.90", "-55.90", "-55.90"])
        + monthly(["-21.90", "-21.90", "-21.90"], account_id=OTHER_CARD)
    )

    assert len(found) == 2
    assert {item.account_id for item in found} == {CARD, OTHER_CARD}


def test_income_and_internal_movements_are_never_recurring_expenses() -> None:
    """A salary repeats monthly, and a transfer to savings is not owed to anyone."""
    salary = monthly(
        ["8500.00", "8500.00", "8500.00"],
        merchant=None,
        description="SALARIO",
        category=ExpenseCategory.INCOME,
    )
    transfers = monthly(
        ["-800.00", "-800.00", "-800.00"],
        merchant=None,
        description="APLICACAO POUPANCA",
        category=ExpenseCategory.INTERNAL_TRANSFER,
    )

    assert detect(salary + transfers) == ()


def test_results_are_ordered_by_size() -> None:
    found = detect(
        monthly(["-21.90", "-21.90", "-21.90"], merchant="Spotify")
        + monthly(["-2400.00", "-2400.00", "-2400.00"], merchant="Imobiliaria")
        + monthly(["-55.90", "-55.90", "-55.90"], merchant="Netflix")
    )

    assert [item.label for item in found] == ["Imobiliaria", "Netflix", "Spotify"]


def test_the_description_identifies_the_charge_when_there_is_no_merchant() -> None:
    found = detect(
        monthly(["-89.90", "-89.90", "-89.90"], merchant=None, description="ACADEMIA SMART FIT")
    )

    assert len(found) == 1
    assert found[0].signature == "ACADEMIA SMART FIT"
