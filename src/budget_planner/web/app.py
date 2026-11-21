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
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from budget_planner.config import Settings, get_settings
from budget_planner.logging import configure as _configure_logging, get_logger
from budget_planner.services import users as users_service
from budget_planner.services.connections import get_connection
from budget_planner.web import retention_task
from budget_planner.web.errors import register_exception_handlers
from budget_planner.web.middleware.admin import AdminRequiredMiddleware
from budget_planner.web.middleware.auth import AuthRequiredMiddleware
from budget_planner.web.middleware.body_limit import body_limit_middleware
from budget_planner.web.middleware.cache_control import CacheControlMiddleware
from budget_planner.web.middleware.csrf import CSRFMiddleware
from budget_planner.web.middleware.must_change_password import MustChangePasswordMiddleware
from budget_planner.web.middleware.request_id import RequestIdMiddleware
from budget_planner.web.middleware.security_headers import security_headers_middleware
from budget_planner.web.routers import (
    accounts,
    auth,
    budget,
    categories,
    debug,
    dev_components,
    forecast,
    health,
    ledger,
    plan,
    planned,
    recurring,
    settings,
    settings_password,
    settings_security,
    settings_users,
    today,
    transactions,
)
from budget_planner.web.templating import build_jinja_env

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from contextlib import AbstractAsyncContextManager
    from types import FrameType

    from structlog.stdlib import BoundLogger

_STATIC_DIR = Path(__file__).parent / "static"

# ADR-0036 addendum 2026-11-21: loopback is always a legal Host (container
# healthcheck, loopback-only bind); test/IPv6 names only outside production.
_LOOPBACK_HOSTS = ("localhost", "127.0.0.1")
_NON_PRODUCTION_HOSTS = ("testserver", "[::1]")


def allowed_hosts(cfg: Settings) -> list[str]:
    """Host allow-list: ``BUDGET_TRUSTED_HOSTS`` plus loopback (and test hosts off prod)."""
    extra = () if cfg.env == "production" else _NON_PRODUCTION_HOSTS
    return list(dict.fromkeys((*cfg.trusted_hosts, *_LOOPBACK_HOSTS, *extra)))


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
    if not hasattr(signal, "SIGTERM"):
        return

    previous = signal.getsignal(signal.SIGTERM)
    # The installed handler is a ``partial`` of ``_on_sigterm``; seeing one in
    # the slot is the idempotence state (no module-level flag, T-Q263).
    if isinstance(previous, partial) and previous.func is _on_sigterm:
        return

    log = get_logger("budget_planner.lifespan")
    try:
        signal.signal(signal.SIGTERM, partial(_on_sigterm, log, previous))
    except ValueError:
        # ``signal.signal`` only works on the main thread; TestClient
        # paths that import the app from a worker thread hit this.
        return


def _on_sigterm(
    log: BoundLogger,
    previous: Callable[[int, FrameType | None], object] | int | signal.Handlers | None,
    signum: int,
    frame: FrameType | None,
) -> None:
    log.info("sigterm_received", signum=signum)
    # Chain the previous handler so uvicorn's drain still runs.
    if callable(previous):
        previous(signum, frame)


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
        purge_task = retention_task.start(cfg)
        try:
            yield
        finally:
            await retention_task.stop(purge_task)
            _close_app_connections(app)
            # Litestream relies on this drain window: the app has
            # finished writing, Litestream has `stop_grace_period: 30s`
            # to flush remaining WAL (ADR-0034 §6).
            log.info("lifespan_shutdown")

    return _lifespan


def _install_middleware(app: FastAPI, cfg: Settings) -> None:
    """Register the user middleware stack (innermost first, see the order below)."""
    # Middleware order, outermost first (ADR-0033 §5 as amended by ADR-0070 §6):
    #   SecurityHeaders (outermost, wraps the stack) → RequestId → TrustedHost →
    #   body limit → AuthRequired → MustChangePassword →
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
    # T-D55 / ADR-0078 §2: no-store on authenticated responses; inside Auth
    # (user hydrated), outside MustChangePassword so its redirects are covered.
    app.add_middleware(CacheControlMiddleware)
    app.add_middleware(AuthRequiredMiddleware)
    app.add_middleware(body_limit_middleware)  # T-Q235: 413 above MAX_BODY_BYTES
    # T-Q254: Host allow-list, inside RequestId so a 400 still carries X-Request-Id.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts(cfg))
    app.add_middleware(RequestIdMiddleware)


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    _configure_logging()
    # OQ-20 default (2026-11-21): interactive docs and the schema are dev-only.
    is_production = cfg.env == "production"
    app = FastAPI(
        title="Budget Planner",
        version="0.1.0",
        docs_url=None if is_production else "/docs",
        openapi_url=None if is_production else "/openapi.json",
        redoc_url=None,
        lifespan=_make_lifespan(cfg),
    )
    app.state.settings = cfg
    app.state.jinja_env = build_jinja_env(cfg)

    _install_middleware(app, cfg)

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    _register_routers(app, include_dev=not is_production)
    register_exception_handlers(app)

    # T-Q254: SecurityHeaders is the outermost layer, outside ServerErrorMiddleware,
    # so unhandled-exception 500 pages carry the headers. ``add_middleware`` cannot
    # place a layer there, so wrap the finished stack (built here, once, after all
    # routers and handlers are registered).
    app.middleware_stack = security_headers_middleware(app.build_middleware_stack())

    return app


def _register_routers(app: FastAPI, *, include_dev: bool) -> None:
    """Include every router explicitly; a router that fails to import fails startup."""
    # Health first: it must be registered before any auth middleware so
    # /health + /ready stay publicly reachable (ADR-0033 §5).
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(transactions.router)
    app.include_router(accounts.router)
    app.include_router(categories.router)
    app.include_router(planned.router)
    app.include_router(recurring.router)
    app.include_router(budget.router)
    app.include_router(forecast.router)
    app.include_router(settings.router)
    app.include_router(settings_users.router)
    app.include_router(settings_password.router)
    app.include_router(settings_security.router)
    app.include_router(debug.router)
    app.include_router(ledger.router)
    app.include_router(today.router)
    app.include_router(plan.router)
    if include_dev:  # ADR-0053, OQ-20: dev surfaces never ship in production
        app.include_router(dev_components.router)


app = create_app()
