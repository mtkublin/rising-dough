"""``Cache-Control: no-store`` on authenticated responses (T-D55, ADR-0078 §2).

Pure-ASGI middleware. When ``request.state.user`` is populated (by
:class:`~budget_planner.web.middleware.auth.AuthRequiredMiddleware`) and the
path is not under ``/static/``, the response gets ``Cache-Control: no-store``,
replacing any weaker value a route set. Anonymous responses (login page,
``/health``, ``/ready``) and static assets are left untouched.

Position: inside ``AuthRequired`` (so the user is hydrated) and outside
``MustChangePassword`` / ``AdminRequired`` / CSRF so their redirects and 404s
are covered too.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_STATIC_PREFIX = "/static/"
_NO_STORE = "no-store"


def _is_authenticated(scope: Scope) -> bool:
    state = scope.get("state") or {}
    return state.get("user") is not None


class CacheControlMiddleware:
    """Mark every authenticated, non-static response ``no-store``."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(_STATIC_PREFIX):
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start" and _is_authenticated(scope):
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = _NO_STORE
            await send(message)

        await self.app(scope, receive, send_wrapper)
