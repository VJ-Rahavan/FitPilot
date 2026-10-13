"""FitGen MCP tools as LangChain tools, over the official MCP Python SDK (mcp 2.x).

langchain-mcp-adapters can't be used: it imports `mcp.server.fastmcp`, which mcp 2.x
removed (see FRICTION_LOG.md). This wrapper is small and keeps `structuredContent`: each
tool returns (spoken text, artifact), and the artifact carries the UI components.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import StructuredTool
from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.types import CallToolResult, Tool

logger = logging.getLogger("fitgen.client")

# Spoken instead of SDK-level errors (argument validation tracebacks, transport failures).
DIDNT_CATCH = "Sorry, I didn't catch that. Could you say it again?"
UNREACHABLE = "Sorry, I couldn't reach FitGen just now. Please try again."


@asynccontextmanager
async def mcp_session(url: str, api_key: str = "") -> AsyncIterator[ClientSession]:
    """An initialized session to the FitGen MCP server (Streamable HTTP)."""
    headers = {"x-api-key": api_key} if api_key else None
    http = create_mcp_http_client(headers=headers)
    async with http, streamable_http_client(url, http_client=http) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@dataclass(frozen=True)
class ToolOutput:
    """One tool call's result, as the web app needs it."""

    text: str
    components: list[dict[str, Any]]
    display: str
    is_error: bool

    def as_artifact(self) -> dict[str, Any]:
        return {
            "components": self.components,
            "display": self.display,
            "is_error": self.is_error,
        }


def to_output(result: CallToolResult) -> ToolOutput:
    text = "\n".join(c.text for c in result.content if c.type == "text")
    if result.is_error and text.startswith("Error executing tool"):
        # The SDK's own error (e.g. a pydantic argument error), not FitGen's spoken text.
        logger.warning("tool error: %s", text)
        text = DIDNT_CATCH
    structured = result.structured_content or {}
    return ToolOutput(
        text=text,
        components=list(structured.get("components", [])),
        display=structured.get("display", "fragment"),
        is_error=bool(result.is_error),
    )


async def call_tool(session: ClientSession, name: str, arguments: dict[str, Any]) -> ToolOutput:
    return to_output(await session.call_tool(name, arguments))


def _langchain_tool(session: ClientSession, tool: Tool) -> StructuredTool:
    async def run(**arguments: Any) -> tuple[str, dict[str, Any]]:
        try:
            output = await call_tool(session, tool.name, arguments)
        except Exception:
            # Always answer the tool call: an unanswered call in the conversation memory
            # would make the model provider reject every later turn.
            logger.exception("tool %s failed", tool.name)
            output = ToolOutput(UNREACHABLE, [], "fragment", True)
        # FitGen's errors are spoken questions ("Did you mean bench press?"); with
        # return_direct they go straight to the user, and their components still show.
        return output.text, output.as_artifact()

    return StructuredTool(
        name=tool.name,
        description=tool.description or "",
        args_schema=_without_titles(tool.input_schema),
        coroutine=run,
        response_format="content_and_artifact",
        # FitGen's text is already the voice-complete answer: speak it as-is and end the
        # turn. One LLM call per turn (half the latency and tokens), no paraphrasing, and
        # no follow-up tool the user didn't ask for.
        return_direct=True,
    )


def _without_titles(node: Any) -> Any:
    """JSON schema minus auto-generated `title`s (they only cost tokens)."""
    if isinstance(node, dict):
        return {
            k: _without_titles(v)
            for k, v in node.items()
            if not (k == "title" and isinstance(v, str))
        }
    if isinstance(node, list):
        return [_without_titles(v) for v in node]
    return node


async def load_tools(session: ClientSession) -> list[StructuredTool]:
    """Every tool the server offers, except the connectivity `ping`."""
    listed = await session.list_tools()
    return [_langchain_tool(session, t) for t in listed.tools if t.name != "ping"]
