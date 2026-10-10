"""Tool definitions as an MCP client (Alexa) sees them. No database needed."""

import httpx2
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from server.tools.registry import WIDGET_URI

UI_TOOLS = {
    "log_workout",
    "log_body_metric",
    "undo_last_log",
    "get_todays_workout",
    "get_weekly_summary",
    "get_exercise_progress",
}


async def _with_session(url, fn):
    async with httpx2.AsyncClient() as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)


async def test_tools_listed_with_widget_metadata(mcp_url):
    tools = await _with_session(mcp_url, lambda s: s.list_tools())
    by_name = {t.name: t for t in tools.tools}
    assert UI_TOOLS | {"ping"} == set(by_name)
    for name in UI_TOOLS:
        tool = by_name[name]
        assert tool.meta == {"ui": {"resourceUri": WIDGET_URI}}, name
        assert tool.description and len(tool.description) <= 120, name
    assert by_name["ping"].meta is None


async def test_input_schemas(mcp_url):
    tools = await _with_session(mcp_url, lambda s: s.list_tools())
    schema = {t.name: t.input_schema for t in tools.tools}
    log = schema["log_workout"]
    assert set(log["required"]) == {"exercise", "sets", "reps"}
    assert log["properties"]["sets"]["minimum"] == 1
    assert schema["undo_last_log"].get("properties", {}) == {}
    assert schema["get_weekly_summary"]["properties"]["weeks_ago"]["default"] == 0


async def test_widget_resource(mcp_url):
    async def read(session):
        listed = await session.list_resources()
        contents = await session.read_resource(WIDGET_URI)
        return listed, contents

    listed, contents = await _with_session(mcp_url, read)
    resource = next(r for r in listed.resources if r.uri == WIDGET_URI)
    assert resource.mime_type == "text/html;profile=mcp-app"
    assert resource.meta == {"ui": {"csp": {}}}
    assert contents.contents[0].mime_type == "text/html;profile=mcp-app"
    assert "<html" in contents.contents[0].text


async def test_invalid_arguments_rejected(mcp_url):
    result = await _with_session(
        mcp_url,
        lambda s: s.call_tool("log_workout", {"exercise": "bench", "sets": 0, "reps": 5}),
    )
    assert result.is_error
