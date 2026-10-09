"""A provider that replays a script.

Tests must not reach a network, and a test about *what the agent does with a tool result*
should not depend on whether a model happened to decide to call that tool. The scripted
provider makes the model's behaviour an input to the test rather than a variable in it.

It also records what it was asked, so a test can assert the agent sent the system prompt,
offered the tools, and fed the tool results back.
"""

from __future__ import annotations

from collections.abc import Sequence

from compass_api.agent.llm.base import LLMMessage, LLMResponse, ToolSpec


class ScriptedLLM:
    """`LLMProvider` that returns queued responses in order."""

    def __init__(self, responses: Sequence[LLMResponse], model: str = "scripted") -> None:
        self._responses = list(responses)
        self._model = model
        #: Every (messages, tools) pair the agent sent, in order.
        self.calls: list[tuple[tuple[LLMMessage, ...], tuple[ToolSpec, ...]]] = []

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        self.calls.append((tuple(messages), tuple(tools)))
        if not self._responses:
            raise AssertionError("the scripted provider ran out of responses")
        return self._responses.pop(0)
