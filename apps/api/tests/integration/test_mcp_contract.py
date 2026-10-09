"""Contract tests: an MCP tool and the HTTP route must answer the same thing.

Both transports call the same services, so a disagreement here means one of them grew a
rule of its own - which is exactly what ADR-0004 forbids. These are the tests that keep
the two honest as the engine changes.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from compass_api.api.deps import USER_ID_HEADER
from compass_api.db.models import User
from compass_api.mcp_server import create_server
from compass_api.mcp_server import tools as mcp_tools
from tests.integration.conftest import WINDOW_END, WINDOW_START

pytestmark = pytest.mark.integration

WINDOW = {"since": WINDOW_START.isoformat(), "until": WINDOW_END.isoformat()}
TARGET_DATE = (date.today() + timedelta(days=548)).isoformat()


@pytest.fixture
def mcp_server(sessionmaker: async_sessionmaker[AsyncSession]) -> Iterator[MCPServer]:
    """A server whose tools use the test session factory.

    The HTTP application owns its own engine inside the test client's loop; the tools get
    one created in this loop. Sharing a single engine across both would be the bug.
    """
    token = mcp_tools.sessionmaker_override.set(sessionmaker)
    yield create_server()
    mcp_tools.sessionmaker_override.reset(token)


async def call(server: MCPServer, name: str, **arguments: Any) -> dict[str, Any]:
    """Invoke a tool and read its JSON payload back."""
    result = await server.call_tool(name, arguments)
    assert isinstance(result, CallToolResult), "a financial tool never asks for input"
    assert not result.is_error, result.content
    block = result.content[0]
    assert isinstance(block, TextContent)
    payload: dict[str, Any] = json.loads(block.text)
    return payload


def _headers(user: User) -> dict[str, str]:
    return {USER_ID_HEADER: str(user.id)}


@pytest.fixture
def synced(api_client: TestClient, user: User) -> User:
    response = api_client.post("/open-finance/sync", json=WINDOW, headers=_headers(user))
    assert response.status_code == 200, response.text
    return user


async def test_cashflow_matches_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    over_http = api_client.get("/insights/cashflow", params=WINDOW, headers=_headers(synced)).json()

    over_mcp = await call(mcp_server, "get_cashflow", user_id=str(synced.id), **WINDOW)

    assert over_mcp["income"] == over_http["income"]
    assert over_mcp["expenses"] == over_http["expenses"]
    assert over_mcp["net"] == over_http["net"]
    assert over_mcp["internal_movements"] == over_http["internal_movements"]
    assert len(over_mcp["months"]) == len(over_http["months"])
    assert [item["category"] for item in over_mcp["by_category"]] == [
        item["category"] for item in over_http["by_category"]
    ]


async def test_saving_capacity_matches_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    over_http = api_client.get(
        "/insights/saving-capacity", params=WINDOW, headers=_headers(synced)
    ).json()

    over_mcp = await call(mcp_server, "calculate_saving_capacity", user_id=str(synced.id), **WINDOW)

    assert over_mcp["sustainable_monthly"] == over_http["sustainable_monthly"]
    assert over_mcp["monthly_median"] == over_http["monthly_median"]
    assert over_mcp["months_considered"] == over_http["months_considered"]


async def test_recurring_expenses_match_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    over_http = api_client.get(
        "/insights/recurring-expenses", params=WINDOW, headers=_headers(synced)
    ).json()

    over_mcp = await call(mcp_server, "detect_recurring_expenses", user_id=str(synced.id), **WINDOW)

    assert over_mcp["monthly_total"] == over_http["monthly_total"]
    assert [item["label"] for item in over_mcp["recurring_expenses"]] == [
        item["label"] for item in over_http["items"]
    ]


async def test_accounts_match_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    over_http = api_client.get("/accounts", headers=_headers(synced)).json()["items"]

    over_mcp = await call(mcp_server, "get_accounts", user_id=str(synced.id))

    assert [item["id"] for item in over_mcp["accounts"]] == [item["id"] for item in over_http]
    assert [item["current_balance"] for item in over_mcp["accounts"]] == [
        item["current_balance"] for item in over_http
    ]


async def test_transactions_match_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    over_http = api_client.get(
        "/transactions", params={**WINDOW, "limit": 5}, headers=_headers(synced)
    ).json()

    over_mcp = await call(mcp_server, "get_transactions", user_id=str(synced.id), limit=5, **WINDOW)

    assert over_mcp["total"] == over_http["total"]
    assert [item["id"] for item in over_mcp["transactions"]] == [
        item["id"] for item in over_http["items"]
    ]
    assert [item["category"] for item in over_mcp["transactions"]] == [
        item["category"] for item in over_http["items"]
    ]


async def test_goal_simulation_matches_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    body = {
        "target_amount": "20000.00",
        "target_date": TARGET_DATE,
        "monthly_contribution": "1000.00",
    }
    over_http = api_client.post("/goals/simulate", json=body, headers=_headers(synced)).json()

    over_mcp = await call(mcp_server, "simulate_goal", user_id=str(synced.id), **body)

    assert over_mcp["monthly_contribution"] == over_http["monthly_contribution"]
    assert over_mcp["contribution_source"] == over_http["contribution_source"]
    assert over_mcp["simulation"]["months_to_target"] == over_http["simulation"]["months_to_target"]
    assert over_mcp["gap"]["required_monthly"] == over_http["gap"]["required_monthly"]


async def test_goal_gap_matches_the_forecast_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    goal = api_client.post(
        "/goals",
        json={"name": "Viagem", "target_amount": "20000.00", "target_date": TARGET_DATE},
        headers=_headers(synced),
    ).json()
    over_http = api_client.get(
        f"/goals/{goal['id']}/forecast",
        params={"monthly_contribution": "900.00"},
        headers=_headers(synced),
    ).json()

    over_mcp = await call(
        mcp_server,
        "calculate_goal_gap",
        user_id=str(synced.id),
        goal_id=goal["id"],
        monthly_contribution="900.00",
    )

    assert over_mcp["gap"]["required_monthly"] == over_http["gap"]["required_monthly"]
    assert over_mcp["gap"]["shortfall_total"] == over_http["gap"]["shortfall_total"]
    assert over_mcp["progress"]["progress_share"] == over_http["progress"]["progress_share"]


async def test_path_comparison_matches_the_http_route(
    mcp_server: MCPServer, api_client: TestClient, synced: User
) -> None:
    goal = api_client.post(
        "/goals",
        json={"name": "Carro", "target_amount": "40000.00", "target_date": TARGET_DATE},
        headers=_headers(synced),
    ).json()
    options = [
        {"label": "plano", "monthly_contribution": "900.00"},
        {"label": "com rendimento", "monthly_contribution": "900.00", "annual_return_rate": "0.11"},
    ]
    over_http = api_client.post(
        f"/goals/{goal['id']}/comparison", json={"options": options}, headers=_headers(synced)
    ).json()

    over_mcp = await call(
        mcp_server,
        "compare_goal_paths",
        user_id=str(synced.id),
        goal_id=goal["id"],
        options=options,
    )

    assert [path["label"] for path in over_mcp["paths"]] == [
        path["label"] for path in over_http["paths"]
    ]
    assert [path["simulation"]["months_to_target"] for path in over_mcp["paths"]] == [
        path["simulation"]["months_to_target"] for path in over_http["paths"]
    ]


# --- isolation and failure -----------------------------------------------------------


async def test_tools_are_scoped_to_the_acting_user(
    mcp_server: MCPServer, synced: User, other_user: User
) -> None:
    mine = await call(mcp_server, "get_accounts", user_id=str(synced.id))
    theirs = await call(mcp_server, "get_accounts", user_id=str(other_user.id))

    assert mine["accounts"]
    assert theirs["accounts"] == []


async def test_amounts_cross_the_boundary_as_exact_strings(
    mcp_server: MCPServer, synced: User
) -> None:
    payload = await call(mcp_server, "get_cashflow", user_id=str(synced.id), **WINDOW)

    assert isinstance(payload["income"], str)
    assert Decimal(payload["income"]) > 0


async def test_an_unknown_goal_is_an_error_not_an_empty_answer(
    mcp_server: MCPServer, synced: User
) -> None:
    """A tool that cannot answer says so; it does not return a plausible nothing."""
    with pytest.raises(ToolError, match="goal not found"):
        await mcp_server.call_tool(
            "calculate_goal_gap",
            {"user_id": str(synced.id), "goal_id": str(uuid.uuid4())},
        )


async def test_a_malformed_user_id_is_rejected(mcp_server: MCPServer) -> None:
    with pytest.raises(ToolError, match="not a valid UUID"):
        await mcp_server.call_tool("get_accounts", {"user_id": "not-a-uuid"})
