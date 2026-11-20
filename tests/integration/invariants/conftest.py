# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Shared multi-currency seed for the G7 differential invariants (ADR-0130 section 3).

The seed is a scratch copy of the tracked anonymised ``data/demo.sqlite`` (PLN accounts, one archived category,
one linked planned row, recurring rules), migrated to head; each invariant adds its own EUR/JPY rows on top.
The production database is never referenced (CLAUDE.md Databases). The services read ``get_settings()`` internally, so
the fixture points ``BUDGET_DATABASE_URL`` at the scratch copy and clears the settings cache around the test.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from budget_planner.config import get_settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_DB = REPO_ROOT / "data" / "demo.sqlite"
USER_ID = 1


def offline_http() -> httpx.Client:
    """An httpx client whose every request fails (forces the cache / stale-fallback path)."""

    def _boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline (invariant harness)", request=request)

    return httpx.Client(transport=httpx.MockTransport(_boom), base_url="https://fx.invalid")


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sqlite3.Connection]:
    """A migrated scratch copy of the demo database, wired into ``get_settings()``."""
    scratch = tmp_path / "invariants.sqlite"
    shutil.copyfile(DEMO_DB, scratch)
    monkeypatch.setenv("BUDGET_DATABASE_URL", f"sqlite:///{scratch}")
    get_settings.cache_clear()
    conn = get_connection(get_settings())
    apply_migrations(conn)
    try:
        yield conn
    finally:
        conn.close()
        get_settings.cache_clear()
