"""FastAPI app with the MCP server mounted at `/mcp` (Streamable HTTP).

Run: uv run uvicorn server.app:app --port 8000
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from server.auth import AuthMiddleware
from server.config import Settings, get_settings
from server.db.session import make_engine
from server.jobs.dispatch import set_queue
from server.jobs.llm import LLMError, build_llm_client
from server.jobs.queue import build_queue
from server.jobs.worker import Worker
from server.mcp_server import mcp

logger = logging.getLogger("fitgen")


async def _start_worker(settings: Settings) -> asyncio.Task | None:
    """Start the background job worker in this process, if enabled and configured."""
    if not settings.worker_enabled:
        return None
    try:
        llm = build_llm_client(settings)
        queue = build_queue(settings)
    except (LLMError, ValueError) as exc:
        logger.warning("Background worker disabled: %s", exc)
        return None
    worker = Worker(
        sessionmaker=async_sessionmaker(make_engine(settings.database_url), expire_on_commit=False),
        queue=queue,
        llm=llm,
        poll_seconds=settings.worker_poll_seconds,
    )
    set_queue(queue)
    try:
        await worker.recover()
    except Exception as exc:  # DB down at startup: the loop keeps retrying
        logger.warning("Could not recover queued jobs at startup: %s", exc)
    return asyncio.create_task(worker.run(), name="fitgen-job-worker")


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
            worker_task = await _start_worker(settings)
            try:
                yield
            finally:
                if worker_task is not None:
                    worker_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await worker_task
                    set_queue(None)

    app = FastAPI(title="FitGen MCP server", lifespan=lifespan)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    # Mounted at the root (after FastAPI's own routes) so the endpoint is exactly /mcp.
    app.mount("/", AuthMiddleware(mcp_app, settings))
    return app


app = create_app()
