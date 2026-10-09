"""The MCP surface: what is exposed, and how results are serialised.

No database here - this is about the contract the agent sees.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

import pytest

from compass_api.mcp_server import create_server
from compass_api.mcp_server.serialization import to_jsonable
from compass_api.mcp_server.tools import FINANCIAL_TOOLS

EXPECTED_TOOLS = {
    "get_accounts",
    "get_transactions",
    "get_cashflow",
    "detect_recurring_expenses",
    "calculate_saving_capacity",
    "list_goals",
    "simulate_goal",
    "calculate_goal_gap",
    "compare_goal_paths",
}


async def test_every_declared_tool_is_registered() -> None:
    tools = await create_server().list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    assert len(tools) == len(FINANCIAL_TOOLS)


async def test_every_tool_describes_itself() -> None:
    """The description is the docstring, so a tool cannot drift from what it says."""
    for tool in await create_server().list_tools():
        assert tool.description, f"{tool.name} has no description"


async def test_every_tool_requires_the_acting_user() -> None:
    """Authentication does not exist yet, so isolation depends on this argument."""
    for tool in await create_server().list_tools():
        assert "user_id" in tool.input_schema["required"], tool.name


async def test_schemas_come_from_the_type_hints() -> None:
    schema = {tool.name: tool.input_schema for tool in await create_server().list_tools()}

    simulate = schema["simulate_goal"]
    assert simulate["required"] == ["user_id", "target_amount"]
    assert simulate["properties"]["annual_return_rate"]["default"] == "0"
    assert set(schema["get_transactions"]["properties"]) == {
        "user_id",
        "since",
        "until",
        "account_id",
        "limit",
    }


async def test_server_instructs_the_agent_not_to_do_arithmetic() -> None:
    """The whole point of the tool layer, stated where a model will read it."""
    server = create_server()

    assert server.instructions is not None
    assert "Do not compute" in server.instructions


# --- serialisation -------------------------------------------------------------------


class _Colour(StrEnum):
    RED = "RED"


@dataclass(frozen=True)
class _Inner:
    amount: Decimal


@dataclass(frozen=True)
class _Outer:
    id: uuid.UUID
    when: date
    at: datetime
    colour: _Colour
    inner: _Inner
    items: tuple[_Inner, ...]
    nothing: str | None


def test_amounts_serialise_as_strings() -> None:
    """A JSON number would hand the consumer a float to round badly."""
    assert to_jsonable(Decimal("2400.00")) == "2400.00"
    assert to_jsonable(Decimal("-0.01")) == "-0.01"


def test_nested_values_convert_recursively() -> None:
    identifier = uuid.uuid4()

    payload = to_jsonable(
        _Outer(
            id=identifier,
            when=date(2026, 6, 15),
            at=datetime(2026, 6, 15, 12, 30),
            colour=_Colour.RED,
            inner=_Inner(Decimal("1.50")),
            items=(_Inner(Decimal("2.50")),),
            nothing=None,
        )
    )

    assert payload == {
        "id": str(identifier),
        "when": "2026-06-15",
        "at": "2026-06-15T12:30:00",
        "colour": "RED",
        "inner": {"amount": "1.50"},
        "items": [{"amount": "2.50"}],
        "nothing": None,
    }


@pytest.mark.parametrize("value", [1, 1.5, "text", True, None])
def test_primitives_pass_through(value: object) -> None:
    assert to_jsonable(value) == value
