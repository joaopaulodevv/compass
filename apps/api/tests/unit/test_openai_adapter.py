"""The OpenAI translation layer.

The network call cannot be tested without a network, but the translation can - and that
is where the bugs live. A tool call serialised wrongly fails at runtime with a message
from a vendor's API, which is a bad place to learn about it.
"""

from __future__ import annotations

import json

import pytest

from compass_api.agent.llm.base import LLMMessage, Role, ToolCall, ToolSpec
from compass_api.agent.llm.openai import _parse_arguments, _to_wire, _tool_to_wire


def test_a_user_message_is_role_and_content() -> None:
    assert _to_wire(LLMMessage.user("ola")) == {"role": "user", "content": "ola"}


def test_a_system_message_keeps_its_role() -> None:
    assert _to_wire(LLMMessage.system("regras"))["role"] == "system"


def test_an_assistant_message_with_tool_calls_serialises_arguments_as_json() -> None:
    message = LLMMessage.assistant(
        None, (ToolCall(id="call-1", name="get_cashflow", arguments={"since": "2026-01-01"}),)
    )

    wire = _to_wire(message)

    assert wire["role"] == "assistant"
    assert wire["content"] is None
    assert wire["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {
                "name": "get_cashflow",
                "arguments": json.dumps({"since": "2026-01-01"}),
            },
        }
    ]


def test_an_assistant_message_without_tool_calls_omits_the_key() -> None:
    """Sending an empty list is not the same as sending none."""
    assert "tool_calls" not in _to_wire(LLMMessage.assistant("texto"))


def test_a_tool_result_carries_the_call_it_answers() -> None:
    wire = _to_wire(LLMMessage.tool_result("call-1", '{"income": "8500.00"}'))

    assert wire == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": '{"income": "8500.00"}',
    }


def test_a_tool_result_with_no_content_sends_an_empty_string() -> None:
    assert _to_wire(LLMMessage(role=Role.TOOL, tool_call_id="x"))["content"] == ""


def test_a_tool_spec_becomes_a_function_definition() -> None:
    schema = {"type": "object", "properties": {"since": {"type": "string"}}}

    wire = _tool_to_wire(ToolSpec("get_cashflow", "Income and expenses.", schema))

    assert wire == {
        "type": "function",
        "function": {
            "name": "get_cashflow",
            "description": "Income and expenses.",
            "parameters": schema,
        },
    }


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"since": "2026-01-01"}', {"since": "2026-01-01"}),
        ("{}", {}),
        ("", {}),
        # The model generates this string, so it can be anything.
        ("{not json", {}),
        ("[1, 2]", {}),
        ('"text"', {}),
    ],
)
def test_malformed_tool_arguments_degrade_to_an_empty_call(
    raw: str, expected: dict[str, object]
) -> None:
    """An unreadable call becomes an empty one, which the tool rejects with a message the
    model can act on - better than crashing the turn."""
    assert _parse_arguments(raw) == expected
