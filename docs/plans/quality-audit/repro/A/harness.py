"""Shared harness for the Track A (T-Q04) differential-invariant scripts.

Safety rules (CLAUDE.md "Databases"):

* The only DB these scripts ever open is ``/tmp/audit-A.sqlite``, a fresh copy of
  ``data/demo.sqlite`` made by :func:`fresh_db`. ``data/budget.sqlite`` is never
  referenced; :func:`fresh_db` refuses any other target.
* ``BUDGET_DATABASE_URL`` is exported *before* any ``budget_planner`` import so
  ``get_settings()`` can never fall back to the default prod path.

Import this module first in every script (``import harness``) and call
``fresh_db()`` before touching services.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path

SCRATCH = Path("/tmp/audit-A.sqlite")  # noqa: S108 - audit scratch DB, never prod
os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{SCRATCH}"
os.environ.setdefault("BUDGET_ENV", "dev")

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

import httpx  # noqa: E402

from budget_planner.config import get_settings  # noqa: E402
from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.db.migrate import apply_migrations  # noqa: E402

USER_ID = 1


def fresh_db() -> sqlite3.Connection:
    """Copy demo.sqlite over the scratch DB, migrate it, return a connection."""
    settings = get_settings()
    target = Path(settings.database_url.removeprefix("sqlite:///"))
    if target != SCRATCH or target.name.endswith("budget.sqlite"):
        raise SystemExit(f"refusing to run against {target}")
    for suffix in ("", "-wal", "-shm"):
        Path(f"{SCRATCH}{suffix}").unlink(missing_ok=True)
    shutil.copyfile(REPO_ROOT / "data" / "demo.sqlite", SCRATCH)
    conn = get_connection(settings)
    apply_migrations(conn)
    return conn


def offline_http() -> httpx.Client:
    """An httpx client whose every request fails (forces the cache/stale-fallback path)."""

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline (audit harness)", request=request)

    return httpx.Client(transport=httpx.MockTransport(_boom), base_url="https://fx.invalid")


def banner(title: str) -> None:
    print(f"\n=== {title} ===")


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(' :: ' + detail) if detail else ''}")
    return ok
