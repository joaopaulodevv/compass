"""The MCP server.

Registration is mechanical: every function in `FINANCIAL_TOOLS` becomes a tool, with its
schema derived from the type hints and its description from the docstring. Nothing about
a tool is written twice, so a tool cannot drift from what it does.

Run it over stdio with:

    uv run --directory apps/api python -m compass_api.mcp_server
"""

from __future__ import annotations

import logging

from mcp.server.mcpserver import MCPServer

from compass_api import __version__
from compass_api.core.config import get_settings
from compass_api.core.logging import configure_logging
from compass_api.mcp_server.tools import FINANCIAL_TOOLS

logger = logging.getLogger(__name__)

INSTRUCTIONS = """
Compass exposes a user's own financial data and a deterministic financial engine.

Use these tools for every number. Do not compute balances, cash flow, saving capacity or
goal projections yourself: the tools are exact, reproducible and auditable, and an
arithmetic mistake in financial guidance changes what someone does with their money.

Amounts are strings holding exact decimals, and are signed - negative is money leaving
the account. Every tool needs the acting user's id.
"""


def create_server() -> MCPServer:
    """Build the server with every financial tool registered."""
    server = MCPServer(
        name="compass-financial",
        title="Compass financial tools",
        instructions=INSTRUCTIONS.strip(),
        version=__version__,
    )
    for tool in FINANCIAL_TOOLS:
        server.tool()(tool)
    return server


def main() -> None:
    """Entry point for `python -m compass_api.mcp_server`."""
    configure_logging(get_settings())
    server = create_server()
    logger.info("mcp server starting", extra={"tools": len(FINANCIAL_TOOLS)})
    server.run(transport="stdio")
