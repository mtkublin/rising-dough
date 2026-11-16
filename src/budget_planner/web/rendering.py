"""Template rendering helpers shared by every router.

Keeping this out of `templating.py` so filters remain pure and testable.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse


def is_hx_request(request: Request) -> bool:
    """True when the request originates from an HTMX swap (HX-Request header)."""
    return request.headers.get("hx-request", "").lower() == "true"


def render(
    request: Request,
    template_name: str,
    status_code: int = 200,
    **context: Any,
) -> HTMLResponse:
    """Render a Jinja template, injecting `request` + `url_for` + settings.

    B-03 — When a non-HTMX client requests a route whose template is the
    bare slide-over fragment (``partials/_slideover.html``), transparently
    swap to ``partials/_slideover_page.html``. That template extends
    ``base.html`` and renders the slide-over inside ``#modal-root`` so
    share-link, refresh, and open-in-new-tab work.
    """
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
    if template_name == "partials/_slideover.html" and not is_hx_request(request):
        fragment_html = env.get_template("partials/_slideover.html").render(**base_ctx)
        base_ctx["_slideover_fragment"] = fragment_html
        template_name = "partials/_slideover_page.html"
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
