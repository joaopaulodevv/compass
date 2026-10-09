"""MCP exposure of Compass's financial capabilities.

The package is `mcp_server`, not `mcp`, so it cannot shadow the SDK it imports.
"""

from compass_api.mcp_server.server import create_server

__all__ = ["create_server"]
