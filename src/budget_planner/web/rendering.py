"""Template rendering helpers shared by every router.

Keeping this out of `templating.py` so filters remain pure and testable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse

from budget_planner.web.http_headers import HX_REQUEST


def is_hx_request(request: Request) -> bool:
    """True when the request originates from an HTMX swap (HX-Request header)."""
    return request.headers.get(HX_REQUEST, "").lower() == "true"


def render(
    request: Request,
    template_name: str,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    """Render a Jinja template with keyword context; see :func:`render_context`."""
    return render_context(request, template_name, context, status_code=status_code)


def render_context(
    request: Request,
    template_name: str,
    context: Mapping[str, object],
    *,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a Jinja template, injecting `request` + `url_for` + settings.

    Takes the template keys as one mapping (view-model builders return one).
    """
    env = request.app.state.jinja_env
    settings = request.app.state.settings
    base_ctx: dict[str, object] = {
        "request": request,
        "settings": settings,
        "url_for": request.url_for,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
        "csrf_token": getattr(request.state, "csrf_token", ""),
    }
    base_ctx.update(context)
    html: str = env.get_template(template_name).render(**base_ctx)
    return HTMLResponse(html, status_code=status_code)


def render_str(request: Request, source: str, **context: Any) -> str:
    """Render an inline template source string (test helper mostly)."""
    env = request.app.state.jinja_env
    settings = request.app.state.settings
    base_ctx: dict[str, Any] = {
        "request": request,
        "settings": settings,
        "url_for": request.url_for,
        "csp_nonce": getattr(request.state, "csp_nonce", ""),
        "csrf_token": getattr(request.state, "csrf_token", ""),
    }
    base_ctx.update(context)
    rendered: str = env.from_string(source).render(**base_ctx)
    return rendered
