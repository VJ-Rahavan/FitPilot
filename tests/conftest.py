import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from server.app import create_app
from server.config import Settings

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
