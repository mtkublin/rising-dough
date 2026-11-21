"""Health & readiness endpoints (T-D01).

- ``GET /health`` → 200 iff the process is up. No DB, no auth.
- ``GET /ready``  → 200 iff the configured SQLite file opens and a trivial
  read succeeds; 503 otherwise (T-Q235: no per-probe ``integrity_check``).

- ``GET /health/replication`` → 200 iff the newest Litestream replica object is
  fresh (T-D144, ADR-0119); 503 when stale, missing or unreadable.

All routes stay outside any auth middleware (ADR-0033 §5) so Caddy, the
deploy pipeline, and the external uptime monitor can poll them without
credentials.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from budget_planner.db.connection import get_connection
from budget_planner.services import replication_health

if TYPE_CHECKING:
    from budget_planner.config import Settings

router = APIRouter(tags=["health"])

_logger = logging.getLogger(__name__)


@router.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
def health(request: Request) -> dict[str, str]:
    """Process liveness. Deliberately cheap — no DB, no logging."""
    return {"status": "ok", "version": request.app.version}


@router.api_route("/ready", methods=["GET", "HEAD"], include_in_schema=False)
def ready(request: Request) -> JSONResponse:
    """Readiness probe. 200 iff the DB opens and the schema answers a trivial read.

    Deliberately cheap (T-Q235, Q-035): no ``integrity_check`` per
    unauthenticated probe, and failures are logged, never echoed.
    """
    cfg: Settings = request.app.state.settings
    try:
        conn = get_connection(cfg)
        try:
            conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        finally:
            conn.close()
    except Exception as exc:
        _logger.warning("ready_probe_failed", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": "database unavailable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready", "db": "ok"})


@router.api_route("/health/replication", methods=["GET", "HEAD"], include_in_schema=False)
def replication(request: Request) -> JSONResponse:
    """Replication freshness for the external monitor (ADR-0119). No secrets in the body."""
    cfg: Settings = request.app.state.settings
    if not cfg.replication_status_file:
        return JSONResponse(content=replication_health.disabled().body())
    try:
        raw = replication_health.read_status_text(cfg.replication_status_file)
    except OSError as exc:
        _logger.warning("replication_status_unreadable", exc_info=exc)
        raw = "unreadable"  # not JSON: evaluate() answers "unreadable"
    verdict = replication_health.evaluate(
        raw,
        now=datetime.now(UTC),
        max_age=timedelta(hours=cfg.replication_max_age_hours),
    )
    return JSONResponse(status_code=200 if verdict.ok else 503, content=verdict.body())
