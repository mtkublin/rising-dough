"""FastAPI application entrypoint.

Thin skeleton (T-030): config, Jinja env, static mount. Routers register
themselves here as later Phase 3 tasks (T-031..T-039) land. Business logic
belongs in Phase 2 services, not here.

T-051 wires the per-request correlation id middleware and the domain-error
exception handlers (see `web.errors`).
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from budget_planner.config import Settings, get_settings
from budget_planner.web.errors import register_exception_handlers
from budget_planner.web.middleware.request_id import RequestIdMiddleware
from budget_planner.web.middleware.security_headers import SecurityHeadersMiddleware
from budget_planner.web.rendering import render
from budget_planner.web.templating import build_jinja_env

_HOME_ROUTER_NAME = "home"

_STATIC_DIR = Path(__file__).parent / "static"


def _configure_logging() -> None:
    """Idempotent root-logger config. Keep key=value style so request ids are grep-able."""
    root = logging.getLogger()
    if any(getattr(h, "_bp_configured", False) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
            defaults={"request_id": "-"},
        )
    )
    handler._bp_configured = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    _configure_logging()
    app = FastAPI(
        title="Budget Planner",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = cfg
    app.state.jinja_env = build_jinja_env(cfg)

    # Attach request id first so later middleware / handlers see it.
    app.add_middleware(RequestIdMiddleware)
    # T-D07 — baseline security headers + CSP nonce propagation. Sits right
    # after RequestId and before any future auth/CSRF/rate-limit layers
    # (ADR-0033 §5, ADR-0036 §3).
    app.add_middleware(SecurityHeadersMiddleware)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    _register_routers(app)
    register_exception_handlers(app)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": app.version}

    # Fallback `/` dev index when the home router did not register (shouldn't
    # happen in prod — the home module is in-tree). Kept for test rigs that
    # intentionally skip the home router.
    if not any(getattr(r, "path", None) == "/" for r in app.router.routes):

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def dev_index(request: Request) -> HTMLResponse:
            return render(request, "_dev_index.html")

    return app


_ROUTER_NAMES: tuple[str, ...] = (
    "home",
    "transactions",
    "accounts",
    "categories",
    "planned",
    "recurring",
    "budget",
    "forecast",
    "analytics",
    "settings",
    "ledger",
    "today",
    "plan",
    "dev_components",
)


def _register_routers(app: FastAPI) -> None:
    """Register Phase 3 routers; missing modules (during iterative landing)
    are tolerated so each task can commit atomically."""
    import importlib  # noqa: PLC0415

    for name in _ROUTER_NAMES:
        try:
            mod = importlib.import_module(f"budget_planner.web.routers.{name}")
        except ImportError:  # pragma: no cover
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            app.include_router(router)


app = create_app()
