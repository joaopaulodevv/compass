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

from compass_api.mcp_server import ALL_TOOLS, create_server
from compass_api.mcp_server.serialization import to_jsonable

#: Tools that read the user's own data. Each must require the acting user.
USER_SCOPED_TOOLS = {
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

#: Tools over shared knowledge. The corpus is the same for everyone, so they take no
#: identity - and must not, or a caller could be made to look like someone else.
SHARED_TOOLS = {"search_financial_knowledge"}

EXPECTED_TOOLS = USER_SCOPED_TOOLS | SHARED_TOOLS


async def test_every_declared_tool_is_registered() -> None:
    tools = await create_server().list_tools()

    assert {tool.name for tool in tools} == EXPECTED_TOOLS
    assert len(tools) == len(ALL_TOOLS)


async def test_every_tool_describes_itself() -> None:
    """The description is the docstring, so a tool cannot drift from what it says."""
    for tool in await create_server().list_tools():
        assert tool.description, f"{tool.name} has no description"


async def test_every_user_scoped_tool_requires_the_acting_user() -> None:
    """Authentication does not exist yet, so isolation depends on this argument."""
    for tool in await create_server().list_tools():
        if tool.name in USER_SCOPED_TOOLS:
            assert "user_id" in tool.input_schema["required"], tool.name


async def test_shared_knowledge_tools_take_no_identity() -> None:
    """Nothing user-specific is read, so asking for an identity would only invite one."""
    for tool in await create_server().list_tools():
        if tool.name in SHARED_TOOLS:
            assert "user_id" not in tool.input_schema.get("properties", {}), tool.name


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
    assert "cite what you use" in server.instructions


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
