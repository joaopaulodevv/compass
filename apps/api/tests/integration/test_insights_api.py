"""The computed endpoints, end to end over ingested sandbox data."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from compass_api.api.deps import USER_ID_HEADER
from compass_api.db.models import User
from tests.integration.conftest import WINDOW_END, WINDOW_START

pytestmark = pytest.mark.integration

WINDOW = {"since": WINDOW_START.isoformat(), "until": WINDOW_END.isoformat()}


def _headers(user: User) -> dict[str, str]:
    return {USER_ID_HEADER: str(user.id)}


@pytest.fixture
def synced(api_client: TestClient, user: User) -> User:
    response = api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user))
    assert response.status_code == 200, response.text
    return user


def _cashflow(api_client: TestClient, user: User) -> dict[str, Any]:
    response = api_client.get("/insights/cashflow", params=WINDOW, headers=_headers(user))
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_ingestion_categorises_every_transaction(api_client: TestClient, synced: User) -> None:
    page = api_client.get("/transactions", params={"limit": 200}, headers=_headers(synced)).json()

    assert page["total"] > 0
    assert all(item["category"] for item in page["items"])
    assert all(item["category_rule"] for item in page["items"])

    by_description = {item["description"]: item for item in page["items"]}
    assert by_description["PAGAMENTO CARTAO NUBANK"]["category"] == "CREDIT_CARD_PAYMENT"
    assert by_description["APLICACAO POUPANCA"]["category"] == "INTERNAL_TRANSFER"
    assert by_description["ALUGUEL IMOBILIARIA CENTRO"]["category"] == "HOUSING"
    assert by_description["SALARIO EMPRESA ACME LTDA"]["category"] == "INCOME"


def test_cashflow_reports_income_expenses_and_a_monthly_series(
    api_client: TestClient, synced: User
) -> None:
    body = _cashflow(api_client, synced)

    assert Decimal(body["income"]) > 0
    assert Decimal(body["expenses"]) > 0
    assert Decimal(body["net"]) == Decimal(body["income"]) - Decimal(body["expenses"])
    assert len(body["months"]) >= 6
    assert all(month["is_complete"] for month in body["months"])


def test_cashflow_excludes_card_payments_and_own_transfers(
    api_client: TestClient, synced: User
) -> None:
    """The sandbox pays a card bill every month and also has the card's purchases."""
    body = _cashflow(api_client, synced)

    assert Decimal(body["internal_movements"]) > 0
    assert body["movements_excluded"] > 0
    categories = {total["category"] for total in body["by_category"]}
    assert "CREDIT_CARD_PAYMENT" not in categories
    assert "INTERNAL_TRANSFER" not in categories


def test_category_breakdown_adds_up(api_client: TestClient, synced: User) -> None:
    body = _cashflow(api_client, synced)

    total = sum(Decimal(item["total"]) for item in body["by_category"])
    assert total == Decimal(body["expenses"])
    assert {item["category"] for item in body["by_category"]} >= {
        "HOUSING",
        "GROCERIES",
        "UTILITIES",
    }


def test_recurring_expenses_find_the_monthly_commitments(
    api_client: TestClient, synced: User
) -> None:
    response = api_client.get(
        "/insights/recurring-expenses", params=WINDOW, headers=_headers(synced)
    )

    assert response.status_code == 200
    body = response.json()
    labels = {item["label"] for item in body["items"]}
    assert {"Imobiliaria Centro", "Netflix", "Spotify"} <= labels
    assert Decimal(body["monthly_total"]) > 0
    assert all(item["occurrences"] >= 3 for item in body["items"])
    assert all(item["expected_next"] > item["last_seen"] for item in body["items"])


def test_saving_capacity_is_based_on_complete_months(api_client: TestClient, synced: User) -> None:
    response = api_client.get("/insights/saving-capacity", params=WINDOW, headers=_headers(synced))

    assert response.status_code == 200
    body = response.json()
    assert body["months_considered"] >= 6
    assert len(body["months"]) == body["months_considered"]
    assert Decimal(body["sustainable_monthly"]) > 0
    assert Decimal(body["monthly_minimum"]) <= Decimal(body["monthly_median"])
    assert Decimal(body["monthly_median"]) <= Decimal(body["monthly_maximum"])


def test_saving_capacity_matches_the_cashflow_it_is_derived_from(
    api_client: TestClient, synced: User
) -> None:
    """The figure must be reproducible from the series the user can also see."""
    cashflow = _cashflow(api_client, synced)
    capacity = api_client.get(
        "/insights/saving-capacity", params=WINDOW, headers=_headers(synced)
    ).json()

    nets = sorted(Decimal(month["net"]) for month in cashflow["months"] if month["is_complete"])
    middle = len(nets) // 2
    expected = nets[middle] if len(nets) % 2 else (nets[middle - 1] + nets[middle]) / 2
    # The engine rounds every derived figure to centavos, half away from zero, so an even
    # number of months can land on a half-cent before rounding.
    rounded = expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    assert Decimal(capacity["monthly_median"]) == rounded


def test_insights_are_empty_for_a_user_with_no_data(
    api_client: TestClient, synced: User, other_user: User
) -> None:
    cashflow = _cashflow(api_client, other_user)
    recurring = api_client.get(
        "/insights/recurring-expenses", params=WINDOW, headers=_headers(other_user)
    ).json()
    capacity = api_client.get(
        "/insights/saving-capacity", params=WINDOW, headers=_headers(other_user)
    ).json()

    assert cashflow["income"] == "0.00"
    assert cashflow["months"] == []
    assert recurring["items"] == []
    assert capacity["months_considered"] == 0
    assert capacity["sustainable_monthly"] == "0.00"


def test_window_defaults_to_the_recent_past(api_client: TestClient, synced: User) -> None:
    response = api_client.get("/insights/cashflow", headers=_headers(synced))

    assert response.status_code == 200
    body = response.json()
    assert body["since"] < body["until"]


@pytest.mark.parametrize(
    "path", ["/insights/cashflow", "/insights/recurring-expenses", "/insights/saving-capacity"]
)
def test_inverted_window_is_rejected(api_client: TestClient, user: User, path: str) -> None:
    response = api_client.get(
        path,
        params={"since": WINDOW_END.isoformat(), "until": WINDOW_START.isoformat()},
        headers=_headers(user),
    )

    assert response.status_code == 422
