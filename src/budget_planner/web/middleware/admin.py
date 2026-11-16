"""Admin-only surface guard (T-D17, ADR-0061 §4, ADR-0073 §1).

Every request under ``/settings/users`` (the path itself and anything
below ``/settings/users/``) needs ``request.state.user.is_admin``. Anyone
else gets the app's standard 404 (full page, or the flash fragment for
HTMX), the same response as any unknown path, so the admin surface
cannot be fingerprinted.

Ordering (outermost first, ADR-0070 §6 + ADR-0073 §1): RequestId →
SecurityHeaders → AuthRequired → **AdminRequired** → CSRF → routers.
AuthRequired has already redirected anonymous requests to login and
hydrated ``request.state.user``. Running before CSRF means a non-admin
POST without a token still gets a 404 rather than a revealing 403.
"""

from __future__ import annotations

from typing import Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from budget_planner.domain.errors import NotFoundError
from budget_planner.web.errors import handle_not_found

ADMIN_PATH_PREFIX: Final = "/settings/users"


def is_admin_path(path: str) -> bool:
    """True for ``/settings/users`` and every path below it."""
    return path == ADMIN_PATH_PREFIX or path.startswith(f"{ADMIN_PATH_PREFIX}/")


def is_admin_user(user: object) -> bool:
    """True when ``user`` (``request.state.user``) is an authenticated admin."""
    return bool(getattr(user, "is_admin", False))


class AdminRequiredMiddleware(BaseHTTPMiddleware):
    """Answer 404 to non-admins on the admin subtree."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if is_admin_path(request.url.path) and not is_admin_user(
            getattr(request.state, "user", None)
        ):
            return await handle_not_found(request, NotFoundError(entity="page", entity_id=0))
        return await call_next(request)


__all__ = ["ADMIN_PATH_PREFIX", "AdminRequiredMiddleware", "is_admin_path", "is_admin_user"]
