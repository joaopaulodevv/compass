"""The agent, with the model scripted and no database in sight.

What is being tested is the agent's behaviour - which tools it offers, what it does with
a result, what happens when it runs out of budget - not whether a model happens to behave.
Making the model an input is the only way those assertions mean anything.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from compass_api.agent.graph import NO_ANSWER, FinancialAgent
from compass_api.agent.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMResponse,
    Role,
    TokenUsage,
    ToolCall,
)
from compass_api.agent.llm.scripted import ScriptedLLM
from compass_api.agent.prompt import SYSTEM_PROMPT
from compass_api.agent.toolbox import FinancialToolbox

USER_ID = uuid.uuid4()
QUESTION = [LLMMessage.system(SYSTEM_PROMPT), LLMMessage.user("quanto posso guardar?")]


def spy_server(result: dict[str, Any] | None = None) -> tuple[MCPServer, dict[str, Any]]:
    """A server with one tool that records how it was called."""
    captured: dict[str, Any] = {}
    server = MCPServer(name="spy")

    @server.tool()
    async def get_cashflow(user_id: str, since: str | None = None) -> dict[str, Any]:
        """Income and expenses over a window."""
        captured["user_id"] = user_id
        captured["since"] = since
        return result or {"income": "8500.00"}

    @server.tool()
    async def exploding(user_id: str) -> dict[str, Any]:
        """Always fails."""
        raise ToolError("the provider is unavailable")

    return server, captured


# --- the toolbox ---------------------------------------------------------------------


async def test_the_model_is_never_offered_the_identity_argument() -> None:
    """Isolation is structural: an argument the model cannot see cannot be misused."""
    server, _ = spy_server()

    specs = await FinancialToolbox(server).specs()

    cashflow = next(spec for spec in specs if spec.name == "get_cashflow")
    assert "user_id" not in cashflow.input_schema["properties"]
    assert "user_id" not in cashflow.input_schema["required"]
    assert "since" in cashflow.input_schema["properties"]


async def test_a_tool_that_takes_no_identity_is_called_without_one() -> None:
    """Knowledge is shared; injecting an identity would be a type error, and offering one
    would let the model smuggle one in."""
    captured: dict[str, Any] = {}
    server = MCPServer(name="shared")

    @server.tool()
    async def search_financial_knowledge(query: str) -> dict[str, Any]:
        """Search shared knowledge."""
        captured["query"] = query
        return {"results": []}

    toolbox = FinancialToolbox(server)
    await toolbox.specs()
    output = await toolbox.invoke(
        ToolCall(
            id="1",
            name="search_financial_knowledge",
            arguments={"query": "liquidez", "user_id": str(uuid.uuid4())},
        ),
        USER_ID,
    )

    assert captured["query"] == "liquidez"
    assert "error" not in json.loads(output)


async def test_the_identity_is_injected_on_every_call() -> None:
    server, captured = spy_server()

    await FinancialToolbox(server).invoke(
        ToolCall(id="1", name="get_cashflow", arguments={"since": "2026-01-01"}), USER_ID
    )

    assert captured["user_id"] == str(USER_ID)
    assert captured["since"] == "2026-01-01"


async def test_an_identity_the_model_supplies_is_overridden() -> None:
    """The model asking for someone else's data gets its own, not theirs."""
    server, captured = spy_server()
    someone_else = uuid.uuid4()

    await FinancialToolbox(server).invoke(
        ToolCall(id="1", name="get_cashflow", arguments={"user_id": str(someone_else)}),
        USER_ID,
    )

    assert captured["user_id"] == str(USER_ID)


async def test_a_failing_tool_answers_the_model_instead_of_crashing_the_turn() -> None:
    server, _ = spy_server()

    output = await FinancialToolbox(server).invoke(
        ToolCall(id="1", name="exploding", arguments={}), USER_ID
    )

    assert "error" in json.loads(output)
    assert "unavailable" in json.loads(output)["error"]


async def test_a_tool_that_crashes_outright_also_answers_the_model() -> None:
    """Whatever the failure, the turn must continue with something the model can read.

    The SDK wraps any exception a tool raises into a `ToolError`, so an unexpected crash
    arrives through the same path as an expected refusal - with a generic message rather
    than the original, which is the SDK's choice and the right one for anything that
    might carry internals.
    """
    server = MCPServer(name="broken")

    @server.tool()
    async def broken(user_id: str) -> dict[str, Any]:
        """Raises something unexpected."""
        raise RuntimeError("connection reset")

    output = await FinancialToolbox(server).invoke(
        ToolCall(id="1", name="broken", arguments={}), USER_ID
    )

    assert "error" in json.loads(output)
    assert "connection reset" not in output


async def test_an_unknown_tool_answers_the_model_too() -> None:
    server, _ = spy_server()

    output = await FinancialToolbox(server).invoke(
        ToolCall(id="1", name="no_such_tool", arguments={}), USER_ID
    )

    assert "error" in json.loads(output)


# --- the graph -----------------------------------------------------------------------


async def test_a_question_needing_no_tools_is_answered_directly() -> None:
    provider = ScriptedLLM([LLMResponse(content="Posso ajudar com suas metas.")])
    server, _ = spy_server()

    turn = await FinancialAgent(provider, FinancialToolbox(server)).run(QUESTION, USER_ID)

    assert turn.answer == "Posso ajudar com suas metas."
    assert turn.tool_calls == ()
    assert turn.model == "scripted"


async def test_a_tool_result_is_fed_back_and_recorded() -> None:
    provider = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=(ToolCall(id="call-1", name="get_cashflow", arguments={}),),
                usage=TokenUsage(prompt_tokens=100, completion_tokens=10),
            ),
            LLMResponse(
                content="Sua receita foi de R$ 8.500,00.",
                usage=TokenUsage(prompt_tokens=200, completion_tokens=20),
            ),
        ]
    )
    server, _ = spy_server({"income": "8500.00"})

    turn = await FinancialAgent(provider, FinancialToolbox(server)).run(QUESTION, USER_ID)

    assert turn.answer == "Sua receita foi de R$ 8.500,00."
    assert turn.tool_calls == ({"name": "get_cashflow", "arguments": {}},)
    # Both calls counted, so cost tracking has somewhere to come from later.
    assert turn.usage.prompt_tokens == 300
    assert turn.usage.completion_tokens == 30

    # The second call must have carried the tool's output back to the model.
    second_messages = provider.calls[1][0]
    tool_messages = [m for m in second_messages if m.role is Role.TOOL]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call-1"
    assert "8500.00" in (tool_messages[0].content or "")


async def test_several_tools_in_one_round_all_run() -> None:
    provider = ScriptedLLM(
        [
            LLMResponse(
                tool_calls=(
                    ToolCall(id="a", name="get_cashflow", arguments={}),
                    ToolCall(id="b", name="get_cashflow", arguments={"since": "2026-01-01"}),
                )
            ),
            LLMResponse(content="Pronto."),
        ]
    )
    server, _ = spy_server()

    turn = await FinancialAgent(provider, FinancialToolbox(server)).run(QUESTION, USER_ID)

    assert len(turn.tool_calls) == 2
    assert len([m for m in provider.calls[1][0] if m.role is Role.TOOL]) == 2


async def test_the_system_prompt_and_tools_reach_the_model() -> None:
    provider = ScriptedLLM([LLMResponse(content="ok")])
    server, _ = spy_server()

    await FinancialAgent(provider, FinancialToolbox(server)).run(QUESTION, USER_ID)

    messages, tools = provider.calls[0]
    assert messages[0].role is Role.SYSTEM
    assert "Never compute" in (messages[0].content or "")
    assert {tool.name for tool in tools} == {"get_cashflow", "exploding"}


async def test_the_tool_budget_is_bounded_and_still_produces_an_answer() -> None:
    """A model stuck in a loop must not leave the user with silence."""
    looping = [
        LLMResponse(tool_calls=(ToolCall(id=str(index), name="get_cashflow", arguments={}),))
        for index in range(3)
    ]
    provider = ScriptedLLM([*looping, LLMResponse(content="Não consegui concluir.")])
    server, _ = spy_server()

    turn = await FinancialAgent(provider, FinancialToolbox(server), max_tool_iterations=3).run(
        QUESTION, USER_ID
    )

    assert turn.answer == "Não consegui concluir."
    assert len(turn.tool_calls) == 3
    # The final call offered no tools at all, which is what forces words.
    assert provider.calls[-1][1] == ()


async def test_a_model_that_keeps_demanding_tools_is_cut_off_with_what_it_said() -> None:
    """The last call offers no tools; if the model asks anyway, the ask is dropped."""
    provider = ScriptedLLM(
        [
            LLMResponse(tool_calls=(ToolCall(id="1", name="get_cashflow", arguments={}),)),
            LLMResponse(
                content="Ainda preciso de dados.",
                tool_calls=(ToolCall(id="2", name="get_cashflow", arguments={}),),
            ),
        ]
    )
    server, _ = spy_server()

    turn = await FinancialAgent(provider, FinancialToolbox(server), max_tool_iterations=1).run(
        QUESTION, USER_ID
    )

    assert turn.answer == "Ainda preciso de dados."
    assert len(turn.tool_calls) == 1


async def test_a_model_that_says_nothing_still_yields_an_answer() -> None:
    provider = ScriptedLLM([LLMResponse(content=None)])
    server, _ = spy_server()

    turn = await FinancialAgent(provider, FinancialToolbox(server)).run(QUESTION, USER_ID)

    assert turn.answer == NO_ANSWER


def test_the_scripted_provider_satisfies_the_protocol() -> None:
    assert isinstance(ScriptedLLM([]), LLMProvider)


async def test_running_out_of_script_is_a_test_failure_not_a_silent_pass() -> None:
    with pytest.raises(AssertionError, match="ran out of responses"):
        await ScriptedLLM([]).complete([], [])


# --- the prompt ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "instruction",
    [
        "Every number you state must come from a tool",
        "Never compute",
        "never invent a rate",
        "Never fill a gap",
        "not regulated financial advice",
    ],
)
def test_the_prompt_states_the_rules_the_architecture_depends_on(instruction: str) -> None:
    """These are not stylistic preferences: they are ADR-0005 in the model's context."""
    assert instruction in SYSTEM_PROMPT
