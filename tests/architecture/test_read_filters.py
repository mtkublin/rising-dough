# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G24: repository reads filter soft-deleted rows and user ids, and mutations go through the audited helpers.

Allowlist: ``allowlists/read_filters.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p05_p06_web_repo.py (p06)`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "read_filters"
TEACH = "G24 read filters: add the deleted_at / user_id predicate or an explicit include_deleted flag, and mutate audited tables only through repositories._shared helpers (ADR-0019, ADR-0022; Q-025, epic E10)."


# The sanctioned home of audit-free UPDATEs (ADR-0022 amendment 2026-11-21, T-Q228): importable
# only by services/recurring.py (test_unaudited_imports.py), which writes the paired audit row.
UNAUDITED_HOME = "src/budget_planner/repositories/_unaudited.py"


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p06-read-filters"), rules=lambda r: r in {"read-no-softdelete", "read-no-user-filter"}
    ) + [
        v
        for v in violations_from_rows(
            rows("p06-unaudited-mutations"), rules=lambda r: r == "mutation-unaudited"
        )
        if v.path != UNAUDITED_HOME
    ]


def test_read_filters_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_read_filters_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "repositories/x.py": 'def read(conn, uid):\n    return conn.execute("SELECT * FROM accounts WHERE user_id = ?", (uid,)).fetchall()\n',
            "../../migrations/001.sql": "CREATE TABLE accounts (\n id INTEGER,\n user_id INTEGER,\n deleted_at TEXT\n);\n",
        }
    )
    hits = [r for r in scanned["p06-read-filters"] if r[1] == "read-no-softdelete"]
    assert hits, "fixture violation not detected by the scanner rule"
