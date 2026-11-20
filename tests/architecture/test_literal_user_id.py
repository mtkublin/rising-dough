# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G7b: no literal user id in ``web/`` and ``services/`` (Q-001).

A hard-coded ``1`` (or ``0``) where a ``user_id`` is expected turns multi-user scoping into a single-user
assumption. Detection: the scanner ``p13_other.py`` rule ``literal-user-id`` (keyword ``user_id=<int>``, positional
int in a ``user_id`` parameter position, or ``user_id = <int>`` assignment). Allowlist: ``allowlists/literal_user_id.toml``.
"""

from __future__ import annotations

from tests.architecture._ratchet import Violation, assert_ratchet, violations_from_rows
from tests.architecture._scan import rows
from tests.architecture.conftest import SyntheticScan

GUARD = "literal_user_id"
HEADER = "G7b literal_user_id: int literal passed as user_id in web/ or services/ (Q-001)."
TEACH = (
    "G7b literal user id: take the id from the `current_user_id` dependency (routers) or the `user_id` parameter "
    "(services); never pass 1 or 0 (Q-001, ADR-0022 user scoping)."
)
PREFIXES = ("src/budget_planner/web/", "src/budget_planner/services/")


def collect() -> list[Violation]:
    return violations_from_rows(
        rows("p13-other"),
        rules=lambda r: r == "literal-user-id",
        keep=lambda loc, _r, _d: loc.startswith(PREFIXES),
    )


def meta(v: Violation) -> tuple[str, str, str, str]:
    if v.path.endswith("routers/budget.py"):
        return "entry", "Q-001", "E09", ""
    return "entry", "Q-002", "E01", ""


def test_literal_user_id_matches_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_literal_user_id_detects_fixture(synthetic_scan: SyntheticScan) -> None:
    source = "def handler(conn, svc):\n    return svc.set_anchor(conn, user_id=1, value=2)\n"
    hits = [
        r
        for r in synthetic_scan({"web/routers/r.py": source})["p13-other"]
        if r[1] == "literal-user-id"
    ]
    assert hits
