"""Bridging the MCP tools into the agent.

The agent does not get its own copy of the tools: it calls the MCP server directly, so
the capabilities the model sees are exactly the ones any other MCP client would see, with
the same schemas and the same behaviour.

Two things happen on the way through, and both are about isolation:

* `user_id` is **stripped from every schema**, so the model is never offered the argument.
* `user_id` is **injected on every call that declares it**, server-side, from the identity
  the request arrived with. Tools that read shared knowledge rather than a user's data -
  the corpus is the same for everyone - never see it.

A model that cannot see the argument cannot be talked into passing someone else's id -
by a crafted question, or by text it read in a transaction description. The isolation is
structural rather than a matter of the prompt behaving.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from compass_api.agent.llm.base import ToolCall, ToolSpec
from compass_api.mcp_server import create_server

logger = logging.getLogger(__name__)

USER_ID_ARGUMENT = "user_id"


class FinancialToolbox:
    """The tools the agent may call, and how their results come back."""

    def __init__(self, server: MCPServer | None = None) -> None:
        self._server = server or create_server()
        self._user_scoped: set[str] | None = None

    async def specs(self) -> tuple[ToolSpec, ...]:
        """Tool definitions for the model, with the identity argument removed."""
        specs = []
        scoped: set[str] = set()
        for tool in await self._server.list_tools():
            if USER_ID_ARGUMENT in tool.input_schema.get("properties", {}):
                scoped.add(tool.name)
            specs.append(
                ToolSpec(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=_without_user_id(tool.input_schema),
                )
            )
        self._user_scoped = scoped
        return tuple(specs)

    async def invoke(self, call: ToolCall, user_id: uuid.UUID) -> str:
        """Run a tool the model asked for and return its result as text.

        A failure comes back as text too, not as an exception: the model asked a question
        and deserves an answer it can react to - retrying differently, or telling the user
        what is missing. Crashing the turn would tell the user nothing.
        """
        arguments = dict(call.arguments)
        if await self._takes_user_id(call.name):
            arguments[USER_ID_ARGUMENT] = str(user_id)
        else:
            # A knowledge tool takes no identity; passing one would be a type error, and
            # the model must not be able to smuggle one in either.
            arguments.pop(USER_ID_ARGUMENT, None)
        try:
            result = await self._server.call_tool(call.name, arguments)
        except ToolError as error:
            logger.info("tool call failed", extra={"tool": call.name, "reason": str(error)})
            return json.dumps({"error": str(error)})
        except Exception:  # pragma: no cover - the SDK wraps tool failures itself
            # A safety net for a failure before the tool body runs. The SDK turns
            # anything a tool raises into ToolError, so this should be unreachable -
            # and an unreachable turn-ending crash is not worth the risk of removing it.
            logger.exception("tool call raised", extra={"tool": call.name})
            return json.dumps({"error": f"tool {call.name} failed"})

        return _result_text(result)

    async def _takes_user_id(self, tool_name: str) -> bool:
        if self._user_scoped is None:
            await self.specs()
        return tool_name in (self._user_scoped or set())


def _without_user_id(schema: dict[str, Any]) -> dict[str, Any]:
    properties = {
        name: value
        for name, value in schema.get("properties", {}).items()
        if name != USER_ID_ARGUMENT
    }
    required = [name for name in schema.get("required", []) if name != USER_ID_ARGUMENT]
    return {**schema, "properties": properties, "required": required}


def _result_text(result: CallToolResult | Any) -> str:
    if not isinstance(result, CallToolResult):
        return json.dumps({"error": "tool asked for input, which is not supported"})
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    return "\n".join(texts) if texts else json.dumps({"result": "no content"})
