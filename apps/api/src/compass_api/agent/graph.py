"""The conversation graph.

Two nodes and one loop: the model thinks, and if it asked for tools they run and the
results go back to it. LangGraph is used for the shape rather than for cleverness - the
state is explicit, and a reader can follow a turn end to end.

The loop is bounded. When the budget runs out the model is asked once more *with no tools
offered*, which forces a final answer in words instead of leaving the user with silence or
an endless chain of calls.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from compass_api.agent.llm.base import (
    LLMMessage,
    LLMProvider,
    TokenUsage,
    ToolCall,
)
from compass_api.agent.toolbox import FinancialToolbox

logger = logging.getLogger(__name__)

#: How many rounds of tool calling a single turn may take. Enough for the worked example
#: in the product brief (profile, cash flow, capacity, simulate, gap) with room to spare.
MAX_TOOL_ITERATIONS = 6

NO_ANSWER = "I could not produce an answer for that."


class AgentState(TypedDict):
    """Everything a turn carries. Explicit, so a trace is readable."""

    user_id: str
    messages: list[LLMMessage]
    pending: list[ToolCall]
    #: Tool calls made during this turn, recorded for the answer's audit trail.
    executed: list[dict[str, Any]]
    iterations: int
    answer: str | None
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True, slots=True)
class AgentTurn:
    """The result of one turn: what to say, and what produced it."""

    answer: str
    tool_calls: tuple[dict[str, Any], ...]
    model: str
    usage: TokenUsage


class FinancialAgent:
    """Runs one conversational turn against the financial tools."""

    def __init__(
        self,
        provider: LLMProvider,
        toolbox: FinancialToolbox | None = None,
        max_tool_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self._provider = provider
        self._toolbox = toolbox or FinancialToolbox()
        self._max_iterations = max_tool_iterations
        self._graph = self._build()

    async def run(self, messages: Sequence[LLMMessage], user_id: uuid.UUID) -> AgentTurn:
        """Answer the conversation so far."""
        final: AgentState = await self._graph.ainvoke(
            AgentState(
                user_id=str(user_id),
                messages=list(messages),
                pending=[],
                executed=[],
                iterations=0,
                answer=None,
                prompt_tokens=0,
                completion_tokens=0,
            )
        )
        return AgentTurn(
            answer=final["answer"] or NO_ANSWER,
            tool_calls=tuple(final["executed"]),
            model=self._provider.model,
            usage=TokenUsage(
                prompt_tokens=final["prompt_tokens"],
                completion_tokens=final["completion_tokens"],
            ),
        )

    def _build(self) -> Any:
        graph: StateGraph[AgentState, None, AgentState, AgentState] = StateGraph(AgentState)
        graph.add_node("think", self._think)
        graph.add_node("act", self._act)
        graph.set_entry_point("think")
        graph.add_conditional_edges("think", self._route, {"act": "act", END: END})
        graph.add_edge("act", "think")
        return graph.compile()

    async def _think(self, state: AgentState) -> dict[str, Any]:
        """Ask the model what to do next."""
        budget_left = state["iterations"] < self._max_iterations
        # Out of budget: offer no tools, so the only possible reply is words.
        tools = await self._toolbox.specs() if budget_left else ()
        response = await self._provider.complete(state["messages"], tools)

        if not budget_left and response.wants_tools:
            logger.warning("tool budget exhausted", extra={"iterations": state["iterations"]})

        return {
            "messages": [
                *state["messages"],
                LLMMessage.assistant(response.content, response.tool_calls),
            ],
            "pending": list(response.tool_calls) if budget_left else [],
            "answer": response.content,
            "prompt_tokens": state["prompt_tokens"] + response.usage.prompt_tokens,
            "completion_tokens": state["completion_tokens"] + response.usage.completion_tokens,
        }

    async def _act(self, state: AgentState) -> dict[str, Any]:
        """Run the tools the model asked for and feed the results back."""
        user_id = uuid.UUID(state["user_id"])
        results: list[LLMMessage] = []
        executed: list[dict[str, Any]] = []

        for call in state["pending"]:
            output = await self._toolbox.invoke(call, user_id)
            results.append(LLMMessage.tool_result(call.id, output))
            executed.append({"name": call.name, "arguments": call.arguments})

        return {
            "messages": [*state["messages"], *results],
            "pending": [],
            "executed": [*state["executed"], *executed],
            "iterations": state["iterations"] + 1,
        }

    def _route(self, state: AgentState) -> str:
        """Tools pending means another round; otherwise the answer stands."""
        return "act" if state["pending"] else END
