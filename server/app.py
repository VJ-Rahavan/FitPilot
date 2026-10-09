"""FastAPI app with the MCP server mounted at `/mcp` (Streamable HTTP).

Run: uv run uvicorn server.app:app --port 8000
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from server.auth import AuthMiddleware
from server.config import Settings, get_settings
from server.mcp_server import mcp


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO)

    # Each call creates a fresh session manager; capture this app's one for the lifespan.
    mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp")
    session_manager = mcp.session_manager

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Mounted Starlette apps don't get their own lifespan run, so start it here.
        async with session_manager.run():
            yield

    app = FastAPI(title="FitGen MCP server", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Mounted at the root (after FastAPI's own routes) so the endpoint is exactly /mcp.
    app.mount("/", AuthMiddleware(mcp_app, settings))
    return app


app = create_app()
