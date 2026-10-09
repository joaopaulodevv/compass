"""The sandbox Open Finance provider.

No database and no network: this is the fixture-reading and date-resolution logic.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from compass_api.domain.open_finance import AccountType
from compass_api.providers.open_finance import MockOpenFinanceProvider, OpenFinanceProvider

REFERENCE_DATE = date(2026, 6, 15)
USER_ID = uuid.uuid4()
WIDE_WINDOW = (date(2025, 1, 1), date(2027, 1, 1))


@pytest.fixture
def provider() -> MockOpenFinanceProvider:
    return MockOpenFinanceProvider(reference_date=REFERENCE_DATE)


def test_mock_satisfies_the_provider_protocol(provider: MockOpenFinanceProvider) -> None:
    """Structural conformance: an adapter never has to import an abstract base of ours."""
    assert isinstance(provider, OpenFinanceProvider)
    assert provider.name == "mock"


async def test_institutions_are_returned(provider: MockOpenFinanceProvider) -> None:
    institutions = await provider.get_institutions(USER_ID)

    assert len(institutions) == 2
    assert all(institution.external_id and institution.name for institution in institutions)


async def test_accounts_cover_the_account_types_the_engine_needs(
    provider: MockOpenFinanceProvider,
) -> None:
    accounts = await provider.get_accounts(USER_ID)

    assert {account.type for account in accounts} == {
        AccountType.CHECKING,
        AccountType.SAVINGS,
        AccountType.CREDIT_CARD,
    }
    assert all(isinstance(account.current_balance, Decimal) for account in accounts)
    # A credit card reports what is owed, as a negative balance.
    card = next(account for account in accounts if account.type is AccountType.CREDIT_CARD)
    assert card.current_balance < 0


async def test_transactions_are_deterministic(provider: MockOpenFinanceProvider) -> None:
    other = MockOpenFinanceProvider(reference_date=REFERENCE_DATE)

    first = await provider.get_transactions(USER_ID, *WIDE_WINDOW)
    second = await other.get_transactions(USER_ID, *WIDE_WINDOW)

    assert first == second


async def test_history_spans_several_months_of_signed_amounts(
    provider: MockOpenFinanceProvider,
) -> None:
    transactions = await provider.get_transactions(USER_ID, *WIDE_WINDOW)

    assert len(transactions) >= 90
    months = {(snapshot.booked_at.year, snapshot.booked_at.month) for snapshot in transactions}
    assert len(months) >= 6
    assert all(isinstance(snapshot.amount, Decimal) for snapshot in transactions)
    assert any(snapshot.amount > 0 for snapshot in transactions), "income is missing"
    assert any(snapshot.amount < 0 for snapshot in transactions), "expenses are missing"
    # Exact to the centavo - the whole reason amounts are decimals and not floats.
    assert any(snapshot.amount == Decimal("-2400.00") for snapshot in transactions)


async def test_external_ids_are_unique(provider: MockOpenFinanceProvider) -> None:
    """They are the idempotency key, so a collision would silently merge two movements."""
    transactions = await provider.get_transactions(USER_ID, *WIDE_WINDOW)

    external_ids = [snapshot.external_id for snapshot in transactions]
    assert len(external_ids) == len(set(external_ids))


async def test_transactions_are_ordered_oldest_first(provider: MockOpenFinanceProvider) -> None:
    transactions = await provider.get_transactions(USER_ID, *WIDE_WINDOW)

    booked = [snapshot.booked_at for snapshot in transactions]
    assert booked == sorted(booked)


async def test_window_is_inclusive_on_both_ends(provider: MockOpenFinanceProvider) -> None:
    everything = await provider.get_transactions(USER_ID, *WIDE_WINDOW)
    earliest = min(snapshot.booked_at for snapshot in everything)
    latest = max(snapshot.booked_at for snapshot in everything)

    # Querying the exact span keeps the first and last movement.
    assert len(await provider.get_transactions(USER_ID, earliest, latest)) == len(everything)
    # Moving either end in by a day drops them.
    inside = await provider.get_transactions(
        USER_ID, earliest + timedelta(days=1), latest - timedelta(days=1)
    )
    assert len(inside) < len(everything)
    assert all(earliest < snapshot.booked_at < latest for snapshot in inside)


async def test_empty_window_returns_nothing(provider: MockOpenFinanceProvider) -> None:
    far_future = date(2030, 1, 1)

    assert await provider.get_transactions(USER_ID, far_future, far_future) == []


async def test_inverted_window_is_rejected(provider: MockOpenFinanceProvider) -> None:
    with pytest.raises(ValueError, match="since"):
        await provider.get_transactions(USER_ID, date(2026, 6, 1), date(2026, 5, 1))


async def test_reference_date_shifts_the_whole_history(
    provider: MockOpenFinanceProvider,
) -> None:
    """Dates are relative, so the fixture never has to be rewritten to stay recent."""
    later = MockOpenFinanceProvider(reference_date=date(2027, 6, 15))

    original = await provider.get_transactions(USER_ID, *WIDE_WINDOW)
    shifted = await later.get_transactions(USER_ID, date(2026, 1, 1), date(2028, 1, 1))

    assert len(shifted) == len(original)
    assert min(snapshot.booked_at for snapshot in shifted).year == 2027


def test_reference_date_defaults_to_today() -> None:
    assert MockOpenFinanceProvider().reference_date == date.today()


async def test_day_is_clamped_to_the_length_of_the_month(tmp_path: Path) -> None:
    """A fixture entry on day 31 must land on the last day of a short month."""
    fixture = {
        "institutions": [{"external_id": "bank", "name": "Bank"}],
        "accounts": [
            {
                "external_id": "acc",
                "institution_external_id": "bank",
                "type": "CHECKING",
                "name": "Account",
                "currency": "BRL",
                "current_balance": "100.00",
            }
        ],
        "transactions": [
            {
                "external_id": "txn-1",
                "account_external_id": "acc",
                "month_offset": 0,
                "day": 31,
                "amount": "-10.00",
                "currency": "BRL",
                "description": "LAST DAY OF FEBRUARY",
                "merchant_name": None,
                "provider_category": None,
            }
        ],
    }
    path = tmp_path / "short-month.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    provider = MockOpenFinanceProvider(reference_date=date(2026, 2, 10), fixture_path=path)

    transactions = await provider.get_transactions(USER_ID, date(2026, 2, 1), date(2026, 2, 28))

    assert [snapshot.booked_at for snapshot in transactions] == [date(2026, 2, 28)]
