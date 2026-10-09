"""The financial endpoints end to end: sync, then read what was ingested."""

from __future__ import annotations

import uuid
from decimal import Decimal

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


def test_sync_reports_what_it_ingested(api_client: TestClient, user: User) -> None:
    response = api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["user_id"] == str(user.id)
    assert body["accounts"] == 3
    assert body["transactions"] > 0
    assert body["transactions_created"] == body["transactions"]
    assert body["transactions_updated"] == 0


def test_second_sync_updates_instead_of_duplicating(api_client: TestClient, user: User) -> None:
    first = api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user)).json()
    second = api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user)).json()

    assert second["transactions_created"] == 0
    assert second["transactions_updated"] == first["transactions"]

    page = api_client.get("/transactions", params={"limit": 1}, headers=_headers(user)).json()
    assert page["total"] == first["transactions"]


def test_accounts_are_returned_with_exact_decimal_amounts(
    api_client: TestClient, synced: User
) -> None:
    response = api_client.get("/accounts", headers=_headers(synced))

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 3
    assert {item["type"] for item in items} == {"CHECKING", "SAVINGS", "CREDIT_CARD"}
    for item in items:
        # Serialised as a string so no client turns centavos into a float.
        assert isinstance(item["current_balance"], str)
        assert Decimal(item["current_balance"]) == Decimal(item["current_balance"])
        assert item["institution"]["name"]


def test_single_account_can_be_fetched(api_client: TestClient, synced: User) -> None:
    listed = api_client.get("/accounts", headers=_headers(synced)).json()["items"][0]

    response = api_client.get(f"/accounts/{listed['id']}", headers=_headers(synced))

    assert response.status_code == 200
    assert response.json() == listed


def test_unknown_account_is_404(api_client: TestClient, synced: User) -> None:
    response = api_client.get(f"/accounts/{uuid.uuid4()}", headers=_headers(synced))

    assert response.status_code == 404


def test_another_users_account_is_404_not_403(
    api_client: TestClient, synced: User, other_user: User
) -> None:
    """Leaking existence is a leak too: an id that is not yours simply does not exist."""
    account_id = api_client.get("/accounts", headers=_headers(synced)).json()["items"][0]["id"]

    response = api_client.get(f"/accounts/{account_id}", headers=_headers(other_user))

    assert response.status_code == 404


def test_transactions_are_paginated_and_signed(api_client: TestClient, synced: User) -> None:
    response = api_client.get("/transactions", params={"limit": 5}, headers=_headers(synced))

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 5
    assert body["limit"] == 5
    assert body["offset"] == 0
    assert body["total"] > 5

    for item in body["items"]:
        amount = Decimal(item["amount"])
        expected = "outflow" if amount < 0 else "inflow"
        assert item["direction"] == expected


def test_transactions_can_be_filtered_by_account(api_client: TestClient, synced: User) -> None:
    account_id = api_client.get("/accounts", headers=_headers(synced)).json()["items"][0]["id"]

    body = api_client.get(
        "/transactions",
        params={"account_id": account_id, "limit": 200},
        headers=_headers(synced),
    ).json()

    assert body["total"] > 0
    assert {item["account_id"] for item in body["items"]} == {account_id}


def test_transactions_can_be_filtered_by_window(api_client: TestClient, synced: User) -> None:
    since = WINDOW_END.replace(day=1).isoformat()

    body = api_client.get(
        "/transactions",
        params={"since": since, "until": WINDOW_END.isoformat(), "limit": 200},
        headers=_headers(synced),
    ).json()

    assert body["total"] > 0
    assert all(since <= item["booked_at"] <= WINDOW_END.isoformat() for item in body["items"])


def test_another_user_sees_nothing(api_client: TestClient, synced: User, other_user: User) -> None:
    accounts = api_client.get("/accounts", headers=_headers(other_user)).json()
    transactions = api_client.get("/transactions", headers=_headers(other_user)).json()

    assert accounts == {"items": []}
    assert transactions["total"] == 0
    assert transactions["items"] == []


def test_sync_for_an_unknown_user_is_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/open-finance/sync", json=WINDOW, headers={USER_ID_HEADER: str(uuid.uuid4())}
    )

    assert response.status_code == 404


def test_sync_without_a_body_uses_the_default_window(api_client: TestClient, user: User) -> None:
    response = api_client.post("/open-finance/sync", headers=_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["since"] < body["until"]
