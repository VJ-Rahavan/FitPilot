"""Starts a real FitGen MCP server (from the repo's root environment) for the client tests.

The server runs against the seeded `fitgen_test` database with API-key auth on, so the
client's x-api-key header is exercised. Skipped when Postgres isn't reachable.
"""

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://fitgen:fitgen@localhost:5434/fitgen_test"
)
API_KEY = "client-test-key"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _db_reachable() -> bool:
    parsed = urlparse(TEST_DATABASE_URL.replace("+asyncpg", ""))
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 5432), timeout=1):
            return True
    except OSError:
        return False


def _server_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    env.update(
        DATABASE_URL=TEST_DATABASE_URL,
        AUTH_MODE="api_key",
        API_KEY=API_KEY,
        WORKER_ENABLED="false",
    )
    return env


@pytest.fixture(scope="session")
def fitgen_url() -> Iterator[str]:
    if not _db_reachable():
        pytest.skip("Postgres not reachable at TEST_DATABASE_URL")
    env = _server_env()
    subprocess.run(
        ["uv", "run", "python", "-m", "server.db.seed", "--reset"],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
    )
    port = _free_port()
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "server.app:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while True:
            try:
                if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            if time.monotonic() > deadline or proc.poll() is not None:
                raise RuntimeError("FitGen server did not start")
            time.sleep(0.2)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
