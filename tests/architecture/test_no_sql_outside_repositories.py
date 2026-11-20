# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G2: no SQL outside ``repositories/`` (amends ADR-0022; the deferred static-analysis rule).

Allowlist: ``allowlists/sql_sites.toml`` (exact ratchet, ADR-0130 section 2). Detection logic is the
audit's scanner ``p05_p06_web_repo.py (p06)`` (ported into ``tests/architecture/_scan``).
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "sql_sites"
TEACH = "G2 no SQL outside repositories: move the statement into a function in src/budget_planner/repositories/ and call it from the service (ADR-0022, ADR-0130; Q-024, Q-074, epic E10)."


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p06-sql-outside-repos"),
        rules=lambda r: r.startswith("sql-"),
        keep=lambda loc, _r, _d: (
            not loc.startswith("src/budget_planner/db/migrate.py")
        ),  # db/migrate.py is the bootstrap
    )


def test_sql_sites_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_sql_sites_detects_fixture_violation(synthetic_scan: SyntheticScan) -> None:
    scanned = synthetic_scan(
        {
            "services/leak.py": 'def f(conn):\n    return conn.execute("SELECT id FROM accounts WHERE user_id = ?", (1,))\n'
        }
    )
    hits = [r for r in scanned["p06-sql-outside-repos"] if r[1].startswith("sql-exec")]
    assert hits, "fixture violation not detected by the scanner rule"
