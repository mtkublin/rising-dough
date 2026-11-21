# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""S3: user-isolation registry for the service layer (ADR-0130; prevention.md S3, Q-015).

Every public ``services/*`` function with a ``user_id`` parameter is either exercised below (user 2's rows never appear
in user 1's results and the reverse; soft-deleted rows stay hidden) or listed in
``tests/architecture/allowlists/user_isolation.toml`` (Q-015 burn-down: add its isolation case here and delete the
entry). The registry check is an exact ratchet in both directions.
"""

from __future__ import annotations

import ast
import sqlite3
from collections.abc import Callable
from datetime import date

import pytest

from budget_planner.config import Settings
from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.recurring import AmountFormula, FormulaTerm
from budget_planner.services import (
    accounts,
    analytics,
    balance,
    budget,
    fortune,
    planned,
    recurring_formula,
)
from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet, repo_rel, src_files
from tests.unit.services.conftest import (
    OTHER_BALANCE,
    OTHER_ID,
    OWNER_BALANCE,
    OWNER_ID,
    World,
)

SERVICES = REPO_ROOT / "src" / "budget_planner" / "services"
TODAY = date(2026, 11, 15)
TEACH = (
    "S3 user isolation: add a case to tests/unit/services/test_user_isolation.py (user 2's rows must never appear for "
    "user 1) and delete the function's entry from tests/architecture/allowlists/user_isolation.toml (Q-015, ADR-0130)."
)


def public_functions_with_user_id(files: dict[str, str]) -> set[tuple[str, str]]:
    """(path, function) for public module-level functions whose parameters include ``user_id``."""
    found: set[tuple[str, str]] = set()
    for path, text in files.items():
        for node in ast.parse(text).body:
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef
            ) and not node.name.startswith("_"):
                params = [a.arg for a in node.args.args + node.args.kwonlyargs]
                if "user_id" in params:
                    found.add((path, node.name))
    return found


def _fortune(conn: sqlite3.Connection, user_id: int) -> int:
    return fortune.compute_fortune(conn, user_id, Settings(_env_file=None)).net_base


def _planned_ids(conn: sqlite3.Connection, user_id: int) -> set[int | None]:
    return {v.persisted_id for v in planned.list_planned(conn, user_id, PlannedFilter())}


def _checked_accounts(conn: sqlite3.Connection, user_id: int) -> set[int]:
    return {r.account_id for r in accounts.last_checked(conn, user_id)}


def _analytics_categories(conn: sqlite3.Connection, user_id: int) -> set[int]:
    bundle = analytics.bundle(conn, user_id, today=TODAY, period="month")
    return {r.category_id for r in bundle.spend_by_category}


def _grid_categories(conn: sqlite3.Connection, user_id: int) -> set[int]:
    return {r.category_id for r in budget.yearly_grid(conn, user_id, 2026)}


def _derived(conn: sqlite3.Connection, user_id: int, account_id: int) -> int:
    try:
        return balance.derive_balance(conn, user_id, account_id)
    except Exception:
        return 0


# function id ("module.function") -> case; registry below must list exactly these ids
COVERED: dict[str, Callable[[sqlite3.Connection, World], None]] = {}


def covers(
    function_id: str,
) -> Callable[
    [Callable[[sqlite3.Connection, World], None]], Callable[[sqlite3.Connection, World], None]
]:
    def register(
        case: Callable[[sqlite3.Connection, World], None],
    ) -> Callable[[sqlite3.Connection, World], None]:
        COVERED[function_id] = case
        return case

    return register


@covers("fortune.compute_fortune")
def _case_fortune(conn: sqlite3.Connection, world: World) -> None:
    own = _fortune(conn, OWNER_ID)
    other = _fortune(conn, OTHER_ID)
    assert own == OWNER_BALANCE - 1_000
    assert other == OTHER_BALANCE - 2_000


@covers("planned.list_planned")
def _case_planned(conn: sqlite3.Connection, world: World) -> None:
    assert _planned_ids(conn, OWNER_ID) == {world.owner.planned_id}
    assert _planned_ids(conn, OTHER_ID) == {world.other.planned_id}


@covers("accounts.last_checked")
def _case_last_checked(conn: sqlite3.Connection, world: World) -> None:
    assert world.other.account_id not in _checked_accounts(conn, OWNER_ID)
    assert world.owner.account_id not in _checked_accounts(conn, OTHER_ID)


@covers("analytics.bundle")
def _case_analytics(conn: sqlite3.Connection, world: World) -> None:
    assert world.other.category_id not in _analytics_categories(conn, OWNER_ID)
    assert world.owner.category_id not in _analytics_categories(conn, OTHER_ID)


@covers("budget.yearly_grid")
def _case_yearly_grid(conn: sqlite3.Connection, world: World) -> None:
    assert world.other.category_id not in _grid_categories(conn, OWNER_ID)
    assert world.owner.category_id not in _grid_categories(conn, OTHER_ID)


@covers("balance.derive_balance")
def _case_derive_balance(conn: sqlite3.Connection, world: World) -> None:
    assert _derived(conn, OWNER_ID, world.owner.account_id) == OWNER_BALANCE - 1_000
    assert _derived(conn, OTHER_ID, world.owner.account_id) != OWNER_BALANCE - 1_000


@covers("recurring_formula.invalid_source_ids")
def _case_invalid_source_ids(conn: sqlite3.Connection, world: World) -> None:
    mine, theirs = world.owner.category_id, world.other.category_id
    assert recurring_formula.invalid_source_ids(conn, OWNER_ID, [(mine,)]) is None
    assert recurring_formula.invalid_source_ids(conn, OWNER_ID, [(mine,), (theirs,)]) == (1, theirs)
    assert recurring_formula.invalid_source_ids(conn, OTHER_ID, [(mine,)]) == (0, mine)


@covers("recurring_formula.compute_savable_amount")
def _case_compute_savable_amount(conn: sqlite3.Connection, world: World) -> None:
    def formula(category_id: int) -> AmountFormula:
        term = FormulaTerm(sign="+", coefficient_bps=10_000, source_category_ids=(category_id,))
        return AmountFormula(terms=(term,))

    with pytest.raises(recurring_formula.FormulaError):
        recurring_formula.compute_savable_amount(
            conn, OWNER_ID, formula(world.other.category_id), 2026, 11
        )
    with pytest.raises(recurring_formula.FormulaError):
        recurring_formula.compute_savable_amount(
            conn, OTHER_ID, formula(world.owner.category_id), 2026, 11
        )


@pytest.mark.parametrize("function_id", sorted(COVERED))
def test_user_data_never_crosses_users(
    function_id: str, conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    COVERED[function_id](conn, world_with_two_users)


def test_soft_deleted_rows_stay_out_of_the_owners_results(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    assert _fortune(conn, OWNER_ID) == OWNER_BALANCE - 1_000
    assert _checked_accounts(conn, OWNER_ID) == {world_with_tombstones.owner.account_id}
    assert _grid_categories(conn, OWNER_ID) == {world_with_tombstones.owner.category_id}


def collect() -> list[Violation]:
    """Public service functions with a ``user_id`` parameter that have no isolation case yet."""
    files = {repo_rel(p): p.read_text(encoding="utf-8") for p in src_files("services")}
    missing = []
    for path, name in sorted(public_functions_with_user_id(files)):
        function_id = f"{path.rsplit('/', 1)[-1].removesuffix('.py')}.{name}"
        if function_id not in COVERED:
            missing.append(Violation(path, 0, name, function_id))
    return missing


def test_isolation_registry_matches_allowlist() -> None:
    assert_ratchet("user_isolation", collect(), TEACH)


def test_registry_detects_function_without_an_isolation_case() -> None:
    src = "def list_things(conn, user_id):\n    return []\n\ndef _private(conn, user_id):\n    return 1\n"
    assert public_functions_with_user_id({"services/x.py": src}) == {
        ("services/x.py", "list_things")
    }
