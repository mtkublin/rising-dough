"""FastAPI application entrypoint.

Thin skeleton (T-030): config, Jinja env, static mount. Routers register
themselves here as later Phase 3 tasks (T-031..T-039) land. Business logic
belongs in Phase 2 services, not here.

T-051 wires the per-request correlation id middleware and the domain-error
exception handlers (see `web.errors`).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from budget_planner.config import Settings, get_settings
from budget_planner.db.connection import get_connection
from budget_planner.web.errors import register_exception_handlers
from budget_planner.web.middleware.request_id import RequestIdMiddleware
from budget_planner.web.rendering import render
from budget_planner.web.templating import build_jinja_env

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

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


def _assert_production_pragmas(cfg: Settings) -> None:
    """ADR-0034 §2: in production, every writer must honour
    ``wal_autocheckpoint = 0``. Fail fast if the DB has drifted away
    from that invariant (e.g. a stray `sqlite3.connect(...)` elsewhere
    silently flipped it back on, or an operator restored a non-Litestream
    DB).

    No-op in dev / test. Opens a short-lived connection so we touch the
    actual DB file, not just the config.
    """
    if cfg.env != "production":
        return
    conn = get_connection(cfg)
    try:
        row = conn.execute("PRAGMA wal_autocheckpoint;").fetchone()
    finally:
        conn.close()
    value = row[0] if row is not None else None
    if value != 0:
        raise RuntimeError(
            "wal_autocheckpoint must be 0 in production (ADR-0034 §2); "
            f"got {value!r}. Check the connection factory and any ad-hoc writers."
        )


def _make_lifespan(cfg: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Build a lifespan context manager bound to the given settings.

    Shutdown is handled fully in T-D15 — the stub here keeps the surface
    small so T-D04 can land independently.
    """

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _assert_production_pragmas(cfg)
        yield

    return _lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    _configure_logging()
    app = FastAPI(
        title="Budget Planner",
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=_make_lifespan(cfg),
    )
    app.state.settings = cfg
    app.state.jinja_env = build_jinja_env(cfg)

    # Attach request id first so later middleware / handlers see it.
    app.add_middleware(RequestIdMiddleware)

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
