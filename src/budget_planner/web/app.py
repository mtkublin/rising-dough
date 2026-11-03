"""FastAPI application entrypoint.

Thin skeleton (T-030): config, Jinja env, static mount. Routers register
themselves here as later Phase 3 tasks (T-031..T-039) land. Business logic
belongs in Phase 2 services, not here.

T-051 wires the per-request correlation id middleware and the domain-error
exception handlers (see `web.errors`).
"""

from __future__ import annotations

import signal
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from budget_planner.config import Settings, get_settings
from budget_planner.db.connection import get_connection
from budget_planner.logging import configure as _configure_logging, get_logger
from budget_planner.services import users as users_service
from budget_planner.web.errors import register_exception_handlers
from budget_planner.web.middleware.admin import AdminRequiredMiddleware
from budget_planner.web.middleware.auth import AuthRequiredMiddleware
from budget_planner.web.middleware.csrf import CSRFMiddleware
from budget_planner.web.middleware.must_change_password import MustChangePasswordMiddleware
from budget_planner.web.middleware.request_id import RequestIdMiddleware
from budget_planner.web.middleware.security_headers import SecurityHeadersMiddleware
from budget_planner.web.rendering import render
from budget_planner.web.templating import build_jinja_env

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager

_HOME_ROUTER_NAME = "home"

_STATIC_DIR = Path(__file__).parent / "static"
_SIGTERM_INSTALLED = False


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


def _install_sigterm_observer() -> None:
    """Register a cheap SIGTERM observer that logs
    ``event="sigterm_received"`` via structlog.

    Uvicorn installs its own asyncio-level SIGTERM handler at server
    startup — the handler flips ``should_exit`` and drives the drain.
    We register a stdlib ``signal.signal`` handler **before** uvicorn's
    server loop replaces it, snapshot the previous handler, and chain
    it so uvicorn's drain still happens. In practice uvicorn's handler
    wins the slot once its server starts; our handler fires once (if
    at all) during the import / lifespan-startup window. That is
    enough to attribute a VM restart to SIGTERM in ``journalctl``.

    Idempotent across repeated ``create_app`` calls (tests). No-op on
    platforms without SIGTERM.
    """
    global _SIGTERM_INSTALLED  # noqa: PLW0603 — module-level idempotence flag
    if _SIGTERM_INSTALLED:
        return
    if not hasattr(signal, "SIGTERM"):
        return

    log = get_logger("budget_planner.lifespan")
    previous = signal.getsignal(signal.SIGTERM)

    def _on_sigterm(signum: int, frame: object | None) -> None:
        log.info("sigterm_received", signum=signum)
        # Chain the previous handler so uvicorn's drain still runs.
        if callable(previous):
            previous(signum, frame)  # type: ignore[arg-type]

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except ValueError:
        # ``signal.signal`` only works on the main thread; TestClient
        # paths that import the app from a worker thread hit this.
        return
    _SIGTERM_INSTALLED = True


def _close_app_connections(app: FastAPI) -> None:
    """Close any sqlite connections parked on ``app.state`` at shutdown.

    v1 does not install a persistent connection; this is future-proofing
    so growing ``app.state`` with a pool later does not accidentally hold
    the WAL open past the Litestream drain window.
    """
    for attr in dir(app.state):
        if attr.startswith("_"):
            continue
        value = getattr(app.state, attr, None)
        if isinstance(value, sqlite3.Connection):
            try:
                value.close()
            except sqlite3.Error:  # pragma: no cover — best-effort cleanup
                continue


def _make_lifespan(cfg: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Build a lifespan context manager bound to the given settings."""

    log = get_logger("budget_planner.lifespan")

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        _assert_production_pragmas(cfg)
        # T-D19 / ADR-0061 §3 / ADR-0069: ensure a live admin exists.
        # Missing credentials with no admin → exit non-zero (fail fast).
        try:
            users_service.bootstrap_admin_at_startup(cfg)
        except (
            users_service.BootstrapAdminMissingEnv,
            users_service.SchemaNotMigratedError,
        ) as exc:
            log.error("admin_bootstrap_failed", error=str(exc))
            raise SystemExit(1) from exc
        _install_sigterm_observer()
        log.info("lifespan_startup", env=cfg.env)
        try:
            yield
        finally:
            _close_app_connections(app)
            # Litestream relies on this drain window: the app has
            # finished writing, Litestream has `stop_grace_period: 30s`
            # to flush remaining WAL (ADR-0034 §6).
            log.info("lifespan_shutdown")

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

    # Middleware order, outermost first (ADR-0033 §5 as amended by ADR-0070 §6):
    #   RequestId → SecurityHeaders → AuthRequired → MustChangePassword →
    #   AdminRequired → CSRF → routers (ADR-0074 §3, ADR-0073 §1).
    # Starlette's ``add_middleware`` wraps each new layer *around* the ones
    # already registered, so registration runs innermost-first:
    # * CSRF (T-D08) is innermost: anonymous POSTs to protected routes are
    #   answered by the auth layer, and the login form still gets a token.
    # * AuthRequired (T-D02b) hydrates ``request.state.user`` and gates
    #   protected routes. Future guards (T-D18 must-change-password, T-D17
    #   admin-only) register between CSRF and AuthRequired.
    # * SecurityHeaders (T-D07) + RequestId wrap everything so every 302 /
    #   401 / 403 still carries the baseline headers and ``X-Request-Id``.
    app.add_middleware(CSRFMiddleware)
    # T-D17 / ADR-0073 §1: 404 for non-admins on /settings/users*. Sits
    # *inside* MustChangePassword so a flagged user gets the same rotation
    # redirect on /settings/users as on any unknown path (no fingerprint);
    # once rotated, non-admins get the standard 404.
    app.add_middleware(AdminRequiredMiddleware)
    app.add_middleware(MustChangePasswordMiddleware)  # T-D18 / ADR-0074 §3
    app.add_middleware(AuthRequiredMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    _register_routers(app)
    register_exception_handlers(app)

    # Fallback `/` dev index when the home router did not register (shouldn't
    # happen in prod — the home module is in-tree). Kept for test rigs that
    # intentionally skip the home router.
    if not any(getattr(r, "path", None) == "/" for r in app.router.routes):

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        def dev_index(request: Request) -> HTMLResponse:
            return render(request, "_dev_index.html")

    return app


_ROUTER_NAMES: tuple[str, ...] = (
    # Health first — it must be registered before any auth middleware so
    # /health + /ready stay publicly reachable (ADR-0033 §5).
    "health",
    # T-D02b — login / logout / passkeys / sessions (ADR-0070).
    "auth",
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
    "settings_users",
    "settings_password",
    "debug",
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
