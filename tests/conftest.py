import asyncio
import os
import socket
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
import uvicorn

from server.app import create_app
from server.config import Settings
from server.db.seed import DEMO_TIMEZONE
from server.db.seed import run as run_seed
from tests.db_support import TEST_DATABASE_URL, db_reachable, reset_db_caches

TEST_API_KEY = "test-key-123"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(settings: Settings) -> Iterator[str]:
    """Run the app in a background uvicorn server; yield its /mcp URL."""
    port = _free_port()
    config = uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@pytest.fixture(scope="session")
def mcp_url() -> Iterator[str]:
    yield from _serve(Settings(auth_mode="none"))


@pytest.fixture(scope="session")
def mcp_url_api_key() -> Iterator[str]:
    yield from _serve(Settings(auth_mode="api_key", api_key=TEST_API_KEY))


@pytest.fixture(scope="module")
def tools_url() -> Iterator[str]:
    """A server backed by a freshly seeded test database (one per test module)."""
    if not asyncio.run(db_reachable()):
        pytest.skip("Postgres not reachable at TEST_DATABASE_URL")
    today = datetime.now(ZoneInfo(DEMO_TIMEZONE)).date()
    asyncio.run(run_seed(TEST_DATABASE_URL, reset=True, today=today))

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    reset_db_caches()
    try:
        yield from _serve(Settings(auth_mode="none", database_url=TEST_DATABASE_URL))
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        reset_db_caches()
