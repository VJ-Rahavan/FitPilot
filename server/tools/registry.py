"""Shared tool plumbing: the MCP Apps extension, the widget resource, and result building.

Tools register on `apps` (at import time); `server.mcp_server` builds the MCPServer with
`extensions=[apps]` afterwards, because extension tools are read at construction.
"""

from collections.abc import Awaitable, Callable

from mcp.server.apps import Apps, ResourceCsp
from mcp.types import CallToolResult, TextContent
from sqlalchemy.ext.asyncio import AsyncSession

from server.auth import get_current_user
from server.catalog.validation import validate_components
from server.db.repository import ENQUEUED_JOBS
from server.db.session import session_scope
from server.jobs.dispatch import dispatch
from server.presenters.workouts import Presentation, present_error
from server.services.context import UserContext, UserFacingError, load_user_context

apps = Apps()

# Placeholder until the real widget build lands in Phase 5 (then: ui://fitgen/widget-<hash>.html).
WIDGET_URI = "ui://fitgen/widget.html"
_PLACEHOLDER_WIDGET = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>FitGen</title></head>
<body><p>FitGen widget is coming soon.</p></body></html>
"""
apps.add_html_resource(
    WIDGET_URI,
    _PLACEHOLDER_WIDGET,
    name="FitGen widget",
    description="Displays FitGen tool results.",
    csp=ResourceCsp(),  # no external domains: the widget is fully self-contained
)


def to_result(p: Presentation, *, is_error: bool = False) -> CallToolResult:
    """Text + validated `structuredContent`. Invalid components raise (a server bug)."""
    return CallToolResult(
        content=[TextContent(type="text", text=p.text)],
        structured_content=validate_components(p.components, p.display),
        is_error=is_error,
    )


async def run_tool(
    handler: Callable[[AsyncSession, UserContext], Awaitable[Presentation]],
) -> CallToolResult:
    """Run a tool body in one DB transaction for the current user.

    A `UserFacingError` rolls the transaction back and becomes a spoken error result.
    Background jobs queued during the call are dispatched once it has committed.
    """
    user = get_current_user()
    try:
        async with session_scope() as db:
            ctx = await load_user_context(db, user.user_id)
            presentation = await handler(db, ctx)
            enqueued = db.info.get(ENQUEUED_JOBS, [])
    except UserFacingError as err:
        return to_result(present_error(err), is_error=True)
    dispatch(enqueued)  # only after the transaction committed
    return to_result(presentation)
