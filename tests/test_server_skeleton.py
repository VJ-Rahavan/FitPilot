import httpx2
import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from server.app import create_app
from server.auth import AuthError, check_api_key
from server.config import Settings
from tests.conftest import TEST_API_KEY


async def _initialize_and_ping(url: str, headers: dict[str, str] | None = None):
    async with httpx2.AsyncClient(headers=headers or {}) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                result = await session.call_tool("ping", {})
                return init, result


async def test_initialize_negotiates_2025_11_25(mcp_url):
    init, _ = await _initialize_and_ping(mcp_url)
    assert init.protocol_version == "2025-11-25"
    assert init.server_info.name == "fitgen"


async def test_ping(mcp_url):
    _, result = await _initialize_and_ping(mcp_url)
    assert not result.is_error
    assert result.content[0].text == "FitGen is up and ready to coach."


@pytest.mark.parametrize("headers", [{}, {"x-api-key": "wrong"}])
async def test_api_key_mode_rejects_missing_or_bad_key(mcp_url_api_key, headers):
    async with httpx2.AsyncClient(headers=headers) as http:
        response = await http.post(
            mcp_url_api_key,
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"accept": "application/json, text/event-stream"},
        )
    assert response.status_code == 401


async def test_api_key_mode_accepts_correct_key(mcp_url_api_key):
    init, result = await _initialize_and_ping(mcp_url_api_key, {"x-api-key": TEST_API_KEY})
    assert init.protocol_version == "2025-11-25"
    assert not result.is_error


def test_check_api_key():
    check_api_key(TEST_API_KEY, TEST_API_KEY)
    for bad in (None, "", "nope"):
        with pytest.raises(AuthError) as exc:
            check_api_key(bad, TEST_API_KEY)
        assert exc.value.status_code == 401


def test_oauth_mode_not_implemented():
    with pytest.raises(NotImplementedError):
        create_app(Settings(auth_mode="oauth"))


def test_api_key_mode_requires_key():
    with pytest.raises(ValueError):
        create_app(Settings(auth_mode="api_key", api_key=""))
