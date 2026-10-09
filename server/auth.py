"""Authentication: the current user and the API-key gate for `/mcp`."""

import hmac
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from server.config import Settings

API_KEY_HEADER = "x-api-key"


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    name: str


# Replaced by a DB lookup of the seeded demo user in Phase 2.
DEMO_USER = CurrentUser(user_id=1, name="Demo User")


def get_current_user() -> CurrentUser:
    """The only way tools obtain a user. Single demo user until OAuth (Phase 10)."""
    return DEMO_USER


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def check_api_key(provided: str | None, expected: str) -> None:
    """Raise a 401 AuthError unless `provided` matches `expected` (constant-time)."""
    if not provided or not expected:
        raise AuthError(401, "Missing or invalid API key")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise AuthError(401, "Missing or invalid API key")


class AuthMiddleware:
    """ASGI middleware around the MCP app; FastAPI dependencies don't reach mounted apps."""

    def __init__(self, app: ASGIApp, settings: Settings):
        if settings.auth_mode == "oauth":
            raise NotImplementedError("AUTH_MODE=oauth is not implemented yet")
        if settings.auth_mode == "api_key" and not settings.api_key:
            raise ValueError("AUTH_MODE=api_key requires API_KEY to be set")
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.settings.auth_mode == "api_key":
            request = Request(scope)
            try:
                check_api_key(request.headers.get(API_KEY_HEADER), self.settings.api_key)
            except AuthError as e:
                response = JSONResponse({"error": e.detail}, status_code=e.status_code)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
