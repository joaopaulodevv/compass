"""The narrow interface Compass depends on, instead of a vendor SDK.

Four things are needed from a language model: send a conversation, offer it tools, get
back either text or tool calls, and know what it cost. Everything else an SDK offers -
streaming helpers, assistants, file uploads, embeddings-as-a-side-effect - is a door the
application does not need open.

Keeping the surface this small is what makes the provider swappable in practice rather
than in principle: an adapter is a hundred lines, and a test double is a class with one
method.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool the model asked for, with the arguments it chose."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """One turn in the conversation sent to the model."""

    role: Role
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    #: Set on a `TOOL` message: which call this is the result of.
    tool_call_id: str | None = None

    @classmethod
    def system(cls, content: str) -> LLMMessage:
        return cls(role=Role.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> LLMMessage:
        return cls(role=Role.USER, content=content)

    @classmethod
    def assistant(cls, content: str | None, tool_calls: tuple[ToolCall, ...] = ()) -> LLMMessage:
        return cls(role=Role.ASSISTANT, content=content, tool_calls=tool_calls)

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> LLMMessage:
        return cls(role=Role.TOOL, content=content, tool_call_id=tool_call_id)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool offered to the model: name, description and JSON Schema for its arguments."""

    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """What a call cost, in tokens. Carried from the start so cost tracking later needs
    no change to the interface - only somewhere to send it."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """What the model replied: text, tool calls, or both."""

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


@runtime_checkable
class LLMProvider(Protocol):
    """A chat model that can call tools."""

    @property
    def model(self) -> str:
        """The model identifier, recorded with the conversation for traceability."""
        ...

    async def complete(
        self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        """Send the conversation and return the model's reply."""
        ...
