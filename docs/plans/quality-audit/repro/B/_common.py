"""Shared scaffolding for the Track B repros (T-Q05).

Builds a scratch DB from ``data/demo.sqlite`` (never ``data/budget.sqlite``),
points the settings at it explicitly, and returns a signed-in CSRF-aware
client. Run from the repo root with ``PYTHONPATH=src:.``.
"""

from __future__ import annotations

import os

# ``budget_planner.web.app`` builds a module-level ``app`` at import time using
# the default settings, so pin the DB URL to a scratch file *before* importing.
os.environ["BUDGET_DATABASE_URL"] = "sqlite:////tmp/audit-B.sqlite"  # noqa: S108
os.environ["BUDGET_ENV"] = "test"

import shutil  # noqa: E402
import sqlite3  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.db.migrate import apply_migrations  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from budget_planner.web.middleware.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME  # noqa: E402
from tests.auth_support import login_cookie  # noqa: E402

DEMO = Path("data/demo.sqlite")
USER_ID = 1


class Client(TestClient):
    """TestClient that attaches the double-submit CSRF header on unsafe verbs."""

    def __init__(self, app: Any) -> None:
        super().__init__(app, base_url="https://testserver", raise_server_exceptions=False)

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any) -> Any:
        if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            token = self.cookies.get(CSRF_COOKIE_NAME)
            if token:
                headers = dict(kwargs.get("headers") or {})
                headers.setdefault(CSRF_HEADER_NAME, token)
                kwargs["headers"] = headers
        return super().request(method, url, *args, **kwargs)


def scratch(name: str) -> tuple[Settings, Path]:
    """Copy the demo DB to ``/tmp/<name>.sqlite`` and return settings for it."""
    dest = Path("/tmp") / f"{name}.sqlite"  # noqa: S108
    if dest.name.endswith("budget.sqlite"):
        raise SystemExit("refusing to touch a prod-named DB")
    for suffix in ("", "-wal", "-shm"):
        Path(str(dest) + suffix).unlink(missing_ok=True)
    shutil.copyfile(DEMO, dest)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{dest.as_posix()}")
    # data/demo.sqlite lags the current schema; bring the scratch copy up to date.
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return settings, dest


def signed_in_client(settings: Settings) -> Client:
    app = create_app(settings=settings)
    client = Client(app)
    name, value = login_cookie(settings)
    client.cookies.set(name, value)
    client.get("/ledger")  # primes the __Host-csrf cookie
    return client


def audit_rows(conn: sqlite3.Connection, entity_type: str, entity_id: int) -> list[Any]:
    return conn.execute(
        "SELECT id, operation, prev_json, new_json FROM audit_log "
        "WHERE entity_type = ? AND entity_id = ? ORDER BY id",
        (entity_type, entity_id),
    ).fetchall()
