"""OpenAI adapter.

The only file in the application that knows OpenAI exists. It translates Compass's
messages into the wire format and the reply back - nothing else leaks.

Never exercised by the test suite: the suite runs with a scripted provider and makes no
network call. This adapter is verified by using it, which is the honest position to take
about code that depends on a remote service.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI

from compass_api.agent.llm.base import (
    LLMMessage,
    LLMResponse,
    Role,
    TokenUsage,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger(__name__)


class OpenAIProvider:
    """`LLMProvider` backed by OpenAI's chat completions."""

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 60.0) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        # The SDK's parameter types are deeply unioned TypedDicts; building them
        # structurally and ignoring the mismatch here keeps the translation readable and
        # confines the vendor's typing to this one call.
        wire_messages: Any = [_to_wire(message) for message in messages]
        wire_tools: Any = [_tool_to_wire(tool) for tool in tools] or None
        response = await self._client.chat.completions.create(
            model=self._model, messages=wire_messages, tools=wire_tools
        )
        choice = response.choices[0].message
        calls = tuple(
            ToolCall(
                id=call.id,
                name=call.function.name,
                arguments=_parse_arguments(call.function.arguments),
            )
            for call in (choice.tool_calls or [])
            if call.type == "function"
        )
        usage = response.usage
        return LLMResponse(
            content=choice.content,
            tool_calls=calls,
            usage=TokenUsage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
            ),
        )


def _parse_arguments(raw: str) -> dict[str, Any]:
    """Tool arguments arrive as a JSON string the model generated, so they can be
    malformed. An unreadable call becomes an empty one, which the tool then rejects with
    a message the model can act on - better than crashing the turn."""
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        logger.warning("model produced unparseable tool arguments")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_wire(message: LLMMessage) -> dict[str, Any]:
    if message.role is Role.TOOL:
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "content": message.content or "",
        }

    payload: dict[str, Any] = {"role": message.role.value, "content": message.content}
    if message.tool_calls:
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return payload


def _tool_to_wire(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }
