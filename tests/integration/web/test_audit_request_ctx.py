"""T-D14 — ``audit_log`` captures the request context for every mutation.

The end-to-end contract this file pins:

1. A POST that creates a new entity writes an audit row whose
   ``ip`` + ``user_agent`` columns reflect the inbound request.
2. The repo-level writer :func:`budget_planner.repositories._shared.write_audit`
   persists every field of :class:`RequestCtx` when called directly.
3. The default-empty context keeps pre-T-D14 behaviour — all four
   new columns land as NULL for legacy call sites.

The web layer dependency ``get_request_ctx`` is still consumed only by
callers that have been plumbed through, so (1) uses the direct writer
path on the server side via a stub router registered on the test app.
That proves the plumbing without requiring every service to be
retrofitted in this commit (T-D14 is scoped additive — see the task
header).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories._shared import transaction, write_audit
from budget_planner.web.app import create_app
from budget_planner.web.deps import get_db, get_request_ctx

pytestmark = pytest.mark.integration


_STUB_USER_AGENT = "T-D14-stub/1.0 (pytest)"


@pytest.fixture
def ctx_settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "audit_ctx.sqlite"
    settings = Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}")
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return settings


# Module-level Depends singletons — ruff B008 forbids inline Depends()
# in parameter defaults (idiomatic for FastAPI routers but flagged in
# tests). The routers have B008 ignored in pyproject; the test tree
# does not.
_DB_DEP = Depends(get_db)
_CTX_DEP = Depends(get_request_ctx)


def _build_app_with_stub(settings: Settings) -> TestClient:
    """Build an app with a stub POST route that writes an audit row.

    The stub takes the ``get_request_ctx`` dependency and threads the
    result into the repo-level writer. That is exactly the plumbing
    shape T-D14 adds; proving it end-to-end here makes the test
    resilient to future service-layer retrofits.
    """
    app = create_app(settings=settings)

    def _stub(
        request: Request,
        conn: sqlite3.Connection = _DB_DEP,
        ctx: RequestCtx = _CTX_DEP,
    ) -> dict[str, int]:
        with transaction(conn):
            write_audit(
                conn,
                entity_type="t_d14_stub",
                entity_id=1,
                operation="create",
                prev=None,
                new={"name": "probe"},
                request_ctx=ctx,
            )
        return {"ok": 1}

    app.post("/_t_d14/stub")(_stub)
    return TestClient(app, base_url="https://testserver")


def _fetch_latest_audit_row(settings: Settings, entity_type: str) -> dict[str, object | None]:
    conn = get_connection(settings)
    try:
        row = conn.execute(
            "SELECT entity_type, entity_id, operation, ip, user_id, "
            "session_id, user_agent FROM audit_log "
            "WHERE entity_type = ? "
            "ORDER BY id DESC LIMIT 1",
            (entity_type,),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None, f"expected an audit row for {entity_type!r}"
    return dict(row)


# ---------------------------------------------------------------------------
# 1. End-to-end: POST → audit row carries IP + user-agent
# ---------------------------------------------------------------------------


def test_post_mutation_persists_request_ctx(ctx_settings: Settings) -> None:
    """A POST through FastAPI threads IP + UA into ``audit_log``.

    TestClient's ASGI transport reports the client as ``testclient`` at
    ``127.0.0.1`` by default. Both must survive the trip to the DB. The
    custom user-agent header overrides httpx's default so we can assert
    on a value this test is in control of.
    """
    client = _build_app_with_stub(ctx_settings)
    try:
        # Prime the CSRF cookie before posting — the T-D08 middleware
        # enforces a double-submit token on every state-changing method.
        # ``/health`` is exempt from CSRF and always registered.
        prime = client.get("/health")
        assert prime.status_code == 200
        csrf = client.cookies.get("__Host-csrf")
        assert csrf is not None, "CSRF cookie must be minted on first GET"
        resp = client.post(
            "/_t_d14/stub",
            headers={"User-Agent": _STUB_USER_AGENT, "X-CSRF-Token": csrf},
        )
        assert resp.status_code == 200, resp.text
    finally:
        client.close()

    row = _fetch_latest_audit_row(ctx_settings, "t_d14_stub")
    assert row["entity_type"] == "t_d14_stub"
    assert row["operation"] == "create"
    assert row["ip"] is not None, "client.host must land in audit_log.ip"
    assert row["user_agent"] == _STUB_USER_AGENT
    # Pre-T-D02 — no auth middleware yet, so session fields stay NULL.
    assert row["user_id"] is None
    assert row["session_id"] is None


# ---------------------------------------------------------------------------
# 2. Direct writer: every field of RequestCtx round-trips through the DB
# ---------------------------------------------------------------------------


def test_write_audit_persists_every_request_ctx_field(ctx_settings: Settings) -> None:
    """Call ``write_audit`` directly and read back every new column."""
    ctx = RequestCtx(
        ip="203.0.113.42",
        user_id=99,
        session_id="sess-abc-123",
        user_agent="curl/8.9.1",
    )
    conn = get_connection(ctx_settings)
    try:
        # Satisfy the audit_log.user_id FK — the pragma is on in `test`,
        # so an orphan reference would raise ``IntegrityError``.
        with transaction(conn):
            conn.execute("INSERT INTO users (id, name) VALUES (99, 'audit-probe')")
        with transaction(conn):
            write_audit(
                conn,
                entity_type="t_d14_direct",
                entity_id=7,
                operation="create",
                prev=None,
                new={"x": 1},
                request_ctx=ctx,
            )
        row = conn.execute(
            "SELECT ip, user_id, session_id, user_agent FROM audit_log "
            "WHERE entity_type = 't_d14_direct' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["ip"] == "203.0.113.42"
    assert row["user_id"] == 99
    assert row["session_id"] == "sess-abc-123"
    assert row["user_agent"] == "curl/8.9.1"


def test_write_audit_default_ctx_leaves_columns_null(ctx_settings: Settings) -> None:
    """Default :meth:`RequestCtx.empty` matches pre-T-D14 behaviour."""
    conn = get_connection(ctx_settings)
    try:
        with transaction(conn):
            write_audit(
                conn,
                entity_type="t_d14_legacy",
                entity_id=1,
                operation="create",
                prev=None,
                new={"n": 0},
            )
        row = conn.execute(
            "SELECT ip, user_id, session_id, user_agent FROM audit_log "
            "WHERE entity_type = 't_d14_legacy' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["ip"] is None
    assert row["user_id"] is None
    assert row["session_id"] is None
    assert row["user_agent"] is None
