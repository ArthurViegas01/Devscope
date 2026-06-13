"""Bearer token authentication as a pure ASGI middleware.

Applied only to the MCP sub-app mount, not to /health or / which are
served by FastAPI routes registered before the mount. Uses constant-time
comparison to prevent timing attacks.
"""

from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

from devscope.logging_config import get_logger

log = get_logger(__name__)


class BearerAuthMiddleware:
    """Reject HTTP requests that do not carry a valid Bearer token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        auth = headers.get(b"authorization", b"").decode("utf-8", errors="replace")

        if not auth or not hmac.compare_digest(auth, self._expected):
            log.warning("auth.unauthorized", path=scope.get("path"))
            await _send_401(send)
            return

        await self._app(scope, receive, send)


async def _send_401(send: Send) -> None:
    body = json.dumps({"error": "unauthorized"}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"www-authenticate", b'Bearer realm="devscope"'),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})
