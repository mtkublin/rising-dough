# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Shared multi-currency seed for the G7 differential invariants (ADR-0130 section 3).

The seed is a scratch copy of the tracked anonymised ``data/demo.sqlite`` (PLN accounts, one archived category,
one linked planned row, recurring rules), migrated to head; each invariant adds its own EUR/JPY rows on top.
The production database is never referenced (CLAUDE.md Databases). The services read ``get_settings()`` internally, so
the fixture points ``BUDGET_DATABASE_URL`` at the scratch copy and clears the settings cache around the test.

Coverage of Track A (``docs/plans/quality-audit/repro/A``): the 16 differential invariants are
INV-1, INV-2, INV-3a/3b/3c, INV-4a/4b, INV-5, INV-6a/6b/6c, INV-7, INV-8a/8b, INV-9, INV-10.
Fifteen are tests in this package. INV-6c (a static count of hard-coded ``/ 100`` in templates and Python) is
deliberately not a test here: it fails today (51 template sites) and a strict ``xfail`` would need a new
``invariants.toml`` entry (the allowlist only shrinks). It is covered by Q-011 / T-Q216 and enforced by the
G6 ``banned_patterns`` and G27 ``money_scope`` guards, whose entries T-Q216 deletes.

Which fix task flips which strict ``xfail`` (each fix task deletes its own ``allowlists/invariants.toml`` entry in
the same change; this package owns no entry). State after T-Q206 and T-Q208 were scheduled:

| Test (file)                                              | Q-id  | Fix task | State                              |
|----------------------------------------------------------|-------|----------|------------------------------------|
| INV-1 foreign expense (test_inv_01)                      | Q-008 | T-Q213   | strict xfail                       |
| INV-2 foreign account (test_inv_02)                      | Q-009 | T-Q214   | strict xfail                       |
| INV-3a spent in base currency (test_inv_03)              | Q-008 | T-Q213   | strict xfail                       |
| INV-3b committed with a linked row (test_inv_03)         | Q-002 | T-Q206   | flipped, plain passing test        |
| INV-3c overdue planned item (test_inv_03)                | Q-030 | T-Q227   | strict xfail                       |
| INV-5 amount parsers (test_inv_05)                       | Q-023 | T-Q233   | strict xfail                       |
| INV-6a exponent table, 2 tests (test_inv_06)             | Q-029 | T-Q216   | strict xfail                       |
| INV-6b /today JPY render (test_inv_06)                   | Q-011 | T-Q216   | strict xfail                       |
| INV-7 period window, 2 tests (test_inv_07)               | Q-003 | T-Q208   | strict xfail (T-Q208 in flight)    |
| INV-8b display-timezone today (test_inv_08)              | Q-031 | T-Q229   | strict xfail                       |
| INV-9 archived category scope (test_inv_09)              | Q-030 | T-Q227   | strict xfail                       |
| INV-10 missing rate (test_inv_10)                        | Q-007 | T-Q212   | strict xfail                       |

INV-4a, INV-4b and INV-8a hold today and are plain passing tests. ``tests/architecture/allowlists/invariants.toml``
is the source of truth for the open entries (one per file and Q-id); a strict ``xfail`` that starts passing fails
the suite, which forces the fix task to flip the test and delete its entry.
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
