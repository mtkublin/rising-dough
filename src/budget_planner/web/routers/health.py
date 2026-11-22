"""Health & readiness endpoints (T-D01).

- ``GET /health`` → 200 iff the process is up. No DB, no auth.
- ``GET /ready``  → 200 iff the configured SQLite file opens and a trivial
  read succeeds; 503 otherwise (T-Q235: no per-probe ``integrity_check``).

- ``GET /health/fx`` → 200 iff every currency used by a live account has a
  recent cached rate (T-Q292, ADR-0146); 503 when stale, missing or unreadable,
  or when the refresh is disabled in production (T-Q307).

- ``GET /health/replication`` → 200 iff the newest Litestream replica object is
  fresh (T-D144, ADR-0119); 503 when stale, missing or unreadable.

All routes stay outside any auth middleware (ADR-0033 §5) so Caddy, the
deploy pipeline, and the external uptime monitor can poll them without
credentials.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from budget_planner import clock
from budget_planner.services import fx_health, replication_health
from budget_planner.services.connections import DB_ERRORS, get_connection, ping
from budget_planner.web.paths import GET_HEAD_METHODS

if TYPE_CHECKING:
    from budget_planner.config import Settings

router = APIRouter(tags=["health"])

_logger = logging.getLogger(__name__)


@router.api_route("/health", methods=list(GET_HEAD_METHODS), include_in_schema=False)
def health(request: Request) -> dict[str, str]:
    """Process liveness. Deliberately cheap — no DB, no logging."""
    return {"status": "ok", "version": request.app.version}


@router.api_route("/ready", methods=list(GET_HEAD_METHODS), include_in_schema=False)
def ready(request: Request) -> JSONResponse:
    """Readiness probe. 200 iff the DB opens and the schema answers a trivial read.

    Deliberately cheap (T-Q235, Q-035): no ``integrity_check`` per
    unauthenticated probe, and failures are logged, never echoed.
    """
    cfg: Settings = request.app.state.settings
    try:
        conn = get_connection(cfg)
        try:
            ping(conn)
        finally:
            conn.close()
    except DB_ERRORS as exc:
        _logger.warning("ready_probe_failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": "database unavailable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "db": "ok"})


@router.api_route("/health/replication", methods=list(GET_HEAD_METHODS), include_in_schema=False)
def replication(request: Request) -> JSONResponse:
    """Replication freshness for the external monitor (ADR-0119). No secrets in the body."""
    cfg: Settings = request.app.state.settings
    verdict = replication_health.check_status_file(
        cfg.replication_status_file,
        max_age_hours=cfg.replication_max_age_hours,
        now=clock.utc_now(),
    )
    return JSONResponse(status_code=200 if verdict.ok else 503, content=verdict.body())


@router.api_route("/health/fx", methods=list(GET_HEAD_METHODS), include_in_schema=False)
def fx_freshness(request: Request) -> JSONResponse:
    """FX cache freshness for the external monitor (ADR-0146). Read-only, no user data."""
    cfg: Settings = request.app.state.settings
    now = clock.utc_now()
    max_age = cfg.fx_max_rate_age_days
    try:
        conn = get_connection(cfg)
        try:
            verdict = fx_health.check(
                conn,
                base_currency=cfg.base_currency,
                refresh_active=cfg.daily_refresh_active(),
                refresh_required=cfg.env == "production",
                today=clock.today_local(cfg),
                max_age_days=max_age,
                now=now,
            )
        finally:
            conn.close()
    except (sqlite3.Error, OSError, ValueError) as exc:
        _logger.warning("fx_health_failed", exc_info=exc)
        verdict = fx_health.unavailable(max_age_days=max_age, now=now)
    return JSONResponse(status_code=200 if verdict.ok else 503, content=verdict.body())
