"""Goals end to end: create, record progress, forecast, compare."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from compass_api.api.deps import USER_ID_HEADER
from compass_api.db.models import User
from tests.integration.conftest import WINDOW_END, WINDOW_START

pytestmark = pytest.mark.integration

TARGET_DATE = (date.today() + timedelta(days=548)).isoformat()


def _headers(user: User) -> dict[str, str]:
    return {USER_ID_HEADER: str(user.id)}


def _create(api_client: TestClient, user: User, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Viagem",
        "target_amount": "20000.00",
        "target_date": TARGET_DATE,
    }
    payload.update(overrides)
    response = api_client.post("/goals", json=payload, headers=_headers(user))
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def goal(api_client: TestClient, user: User) -> dict[str, Any]:
    return _create(api_client, user)


def test_a_goal_is_created_with_its_terms(api_client: TestClient, user: User) -> None:
    body = _create(api_client, user, initial_amount="1500.00")

    assert body["name"] == "Viagem"
    assert body["target_amount"] == "20000.00"
    assert body["status"] == "ACTIVE"
    # A goal starts where it starts: what is already set aside is the current balance.
    assert body["initial_amount"] == "1500.00"
    assert body["current_amount"] == "1500.00"


def test_goal_names_are_unique_per_user(api_client: TestClient, user: User) -> None:
    _create(api_client, user)

    response = api_client.post(
        "/goals",
        json={"name": "Viagem", "target_amount": "500.00"},
        headers=_headers(user),
    )

    assert response.status_code == 409


def test_the_same_name_is_free_for_another_user(
    api_client: TestClient, user: User, other_user: User
) -> None:
    _create(api_client, user)

    assert _create(api_client, other_user)["name"] == "Viagem"


def test_a_goal_for_an_unknown_user_is_404(api_client: TestClient) -> None:
    response = api_client.post(
        "/goals",
        json={"name": "Viagem", "target_amount": "100.00"},
        headers={USER_ID_HEADER: str(uuid.uuid4())},
    )

    assert response.status_code == 404


def test_a_target_date_in_the_past_is_rejected(api_client: TestClient, user: User) -> None:
    response = api_client.post(
        "/goals",
        json={
            "name": "Ontem",
            "target_amount": "100.00",
            "target_date": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=_headers(user),
    )

    assert response.status_code == 422


def test_goals_are_listed_and_fetched_individually(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    listed = api_client.get("/goals", headers=_headers(user)).json()
    fetched = api_client.get(f"/goals/{goal['id']}", headers=_headers(user))

    assert [item["id"] for item in listed["items"]] == [goal["id"]]
    assert fetched.status_code == 200
    assert fetched.json() == goal


def test_another_users_goal_is_404(
    api_client: TestClient, goal: dict[str, Any], other_user: User
) -> None:
    response = api_client.get(f"/goals/{goal['id']}", headers=_headers(other_user))

    assert response.status_code == 404


def test_recording_progress_updates_the_balance(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    response = api_client.patch(
        f"/goals/{goal['id']}", json={"current_amount": "2500.00"}, headers=_headers(user)
    )

    assert response.status_code == 200
    assert response.json()["current_amount"] == "2500.00"
    assert response.json()["status"] == "ACTIVE"


def test_reaching_the_target_achieves_the_goal(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    """The one rule a goal has, applied without the caller asking for it."""
    response = api_client.patch(
        f"/goals/{goal['id']}", json={"current_amount": "20000.00"}, headers=_headers(user)
    )

    assert response.json()["status"] == "ACHIEVED"


def test_forecast_falls_back_to_the_measured_saving_capacity(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    """With no plan of their own, the user is told what their own history supports."""
    api_client.post(
        "/open-finance/sync",
        json={"since": WINDOW_START.isoformat(), "until": WINDOW_END.isoformat()},
        headers=_headers(user),
    )

    body = api_client.get(f"/goals/{goal['id']}/forecast", headers=_headers(user)).json()

    assert body["contribution_source"] == "measured_capacity"
    assert Decimal(body["monthly_contribution"]) > 0
    capacity = api_client.get("/insights/saving-capacity", headers=_headers(user)).json()
    assert body["monthly_contribution"] == capacity["sustainable_monthly"]


def test_forecast_prefers_the_goal_s_own_plan(api_client: TestClient, user: User) -> None:
    goal = _create(api_client, user, monthly_contribution="1200.00")

    body = api_client.get(f"/goals/{goal['id']}/forecast", headers=_headers(user)).json()

    assert body["contribution_source"] == "goal_plan"
    assert body["monthly_contribution"] == "1200.00"


def test_forecast_uses_an_explicit_contribution_when_asked(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    body = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"monthly_contribution": "1000.00"},
        headers=_headers(user),
    ).json()

    assert body["contribution_source"] == "requested"
    assert body["simulation"]["months_to_target"] == 20
    assert body["simulation"]["is_feasible"] is True


def test_forecast_reports_the_gap_against_the_target_date(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    body = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"monthly_contribution": "900.00"},
        headers=_headers(user),
    ).json()

    gap = body["gap"]
    assert gap["months_available"] == 18
    assert Decimal(gap["required_monthly"]) > Decimal("900.00")
    assert Decimal(gap["shortfall_total"]) > 0
    assert gap["on_track"] is False
    assert body["progress"]["progress_share"] == "0.0000"


def test_an_undated_goal_has_no_gap(api_client: TestClient, user: User) -> None:
    goal = _create(api_client, user, name="Reserva", target_date=None)

    body = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"monthly_contribution": "500.00"},
        headers=_headers(user),
    ).json()

    assert body["gap"] is None
    assert body["progress"]["on_track"] is None
    assert body["simulation"]["months_to_target"] == 40


def test_an_expected_return_shortens_the_projection(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    without = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"monthly_contribution": "1000.00"},
        headers=_headers(user),
    ).json()
    with_return = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"monthly_contribution": "1000.00", "annual_return_rate": "0.11"},
        headers=_headers(user),
    ).json()

    assert with_return["simulation"]["months_to_target"] < without["simulation"]["months_to_target"]
    assert Decimal(with_return["simulation"]["total_return"]) > 0


def test_an_absurd_return_rate_is_rejected(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    response = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"annual_return_rate": "5"},
        headers=_headers(user),
    )

    assert response.status_code == 422


def test_paths_are_compared_and_ordered(
    api_client: TestClient, user: User, goal: dict[str, Any]
) -> None:
    response = api_client.post(
        f"/goals/{goal['id']}/comparison",
        json={
            "options": [
                {"label": "conservador", "monthly_contribution": "800.00"},
                {"label": "agressivo", "monthly_contribution": "1600.00"},
                {
                    "label": "com rendimento",
                    "monthly_contribution": "800.00",
                    "annual_return_rate": "0.11",
                },
            ]
        },
        headers=_headers(user),
    )

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert [path["label"] for path in paths] == ["agressivo", "com rendimento", "conservador"]
    months = [path["simulation"]["months_to_target"] for path in paths]
    assert months == sorted(months)


def test_a_goal_can_be_simulated_before_it_exists(api_client: TestClient, user: User) -> None:
    """The first question a user asks needs no record created."""
    response = api_client.post(
        "/goals/simulate",
        json={
            "target_amount": "20000.00",
            "target_date": TARGET_DATE,
            "monthly_contribution": "1000.00",
        },
        headers=_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["contribution_source"] == "requested"
    assert body["simulation"]["months_to_target"] == 20
    assert body["gap"]["on_track"] is False
    assert api_client.get("/goals", headers=_headers(user)).json()["items"] == []


def test_a_draft_simulation_falls_back_to_measured_capacity(
    api_client: TestClient, user: User
) -> None:
    api_client.post(
        "/open-finance/sync",
        json={"since": WINDOW_START.isoformat(), "until": WINDOW_END.isoformat()},
        headers=_headers(user),
    )

    body = api_client.post(
        "/goals/simulate",
        json={"target_amount": "20000.00", "target_date": TARGET_DATE},
        headers=_headers(user),
    ).json()

    assert body["contribution_source"] == "measured_capacity"
    assert Decimal(body["monthly_contribution"]) > 0
    assert body["simulation"]["is_feasible"] is True
