"""The FitGen MCP server instance and its middleware.

mcp 2.x renamed FastMCP to MCPServer; this is the same official SDK server.
"""

import logging
import time
from typing import Any

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import MCPServer

# Importing the tool modules registers their tools on `apps`; that must happen before
# MCPServer is built, since extension tools are read at construction.
from server.tools import logging_tools, review_tools  # noqa: F401
from server.tools.ping import ping
from server.tools.registry import apps

logger = logging.getLogger("fitgen.tools")


async def log_tool_timing(
    ctx: ServerRequestContext[Any, Any], call_next: CallNext
) -> HandlerResult:
    """Log each tool call's name and duration in milliseconds."""
    if ctx.method != "tools/call":
        return await call_next(ctx)
    name = (ctx.params or {}).get("name", "?")
    start = time.perf_counter()
    status = "error"
    try:
        result = await call_next(ctx)
        status = "ok"
        return result
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info("tool=%s status=%s duration_ms=%.1f", name, status, duration_ms)


mcp = MCPServer(
    name="fitgen",
    title="FitGen",
    instructions=(
        "FitGen is a voice-first strength coach. Use its tools to log and review training."
    ),
    version="0.1.0",
    middleware=[log_tool_timing],
    extensions=[apps],
)
mcp.add_tool(ping, description="Check that FitGen is reachable.")
