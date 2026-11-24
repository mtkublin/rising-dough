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
from datetime import date

import pytest

from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings
from budget_planner.domain.accounts import AccountReferences
from budget_planner.domain.errors import ConflictError
from budget_planner.domain.recurring import AmountFormula, FormulaTerm
from budget_planner.services import (
    accounts,
    analytics,
    budget,
    categories,
    fortune,
    fx,
    recurring_formula,
)
from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet, repo_rel, src_files
from tests.formula_fx_support import TARGET_CCY, formula_fx_of
from tests.unit.services import (  # noqa: F401 - importing registers the cases
    _isolation_account_cases,
    _isolation_crud_cases,
    _isolation_ledger_cases,
    _isolation_read_cases,
    _isolation_t266_cases,
    _isolation_t267_cases,
    _isolation_write_cases,
)
from tests.unit.services._isolation_registry import COVERED, covers
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
    return fortune.compute_fortune(
        conn, user_id, fx.converter_for(conn, Settings(_env_file=None), TODAY)
    ).net_base


def _checked_accounts(conn: sqlite3.Connection, user_id: int) -> set[int]:
    return {r.account_id for r in accounts.last_checked(conn, user_id)}


def _analytics_categories(conn: sqlite3.Connection, user_id: int) -> set[int]:
    bundle = analytics.bundle(
        conn,
        user_id,
        fx.converter_for(conn, Settings(_env_file=None), TODAY),
        today=TODAY,
        period="month",
    )
    return {r.category_id for r in bundle.spend_by_category}


def _grid_categories(conn: sqlite3.Connection, user_id: int) -> set[int]:
    return {
        r.category_id
        for r in budget.yearly_grid(conn, user_id, 2099, display_timezone=DEFAULT_DISPLAY_TIMEZONE)
    }  # far after the tombstone archive month (ADR-0136)


@covers("fortune.compute_fortune")
def _case_fortune(conn: sqlite3.Connection, world: World) -> None:
    own = _fortune(conn, OWNER_ID)
    other = _fortune(conn, OTHER_ID)
    assert own == OWNER_BALANCE - 1_000
    assert other == OTHER_BALANCE - 2_000


@covers("accounts.last_checked")
def _case_last_checked(conn: sqlite3.Connection, world: World) -> None:
    assert world.other.account_id not in _checked_accounts(conn, OWNER_ID)
    assert world.owner.account_id not in _checked_accounts(conn, OTHER_ID)


@covers("accounts.archive_account")
def _case_archive_account(conn: sqlite3.Connection, world: World) -> None:
    # The owner cannot archive (or even see) the other user's account: a no-op, nothing leaks or changes.
    accounts.archive_account(conn, OWNER_ID, world.other.account_id)
    assert world.other.account_id in _checked_accounts(conn, OTHER_ID)
    # The owner's own account carries a balance, rules and planned rows: refused, still live.
    with pytest.raises(ConflictError) as err:
        accounts.archive_account(conn, OWNER_ID, world.owner.account_id)
    assert err.value.message == (
        "Cannot archive account: Balance is not zero; 1 transaction uses this account; "
        "1 planned transaction uses this account; 3 recurring rules use this account"
    )
    assert world.owner.account_id in _checked_accounts(conn, OWNER_ID)


@covers("accounts.account_references")
def _case_account_references(conn: sqlite3.Connection, world: World) -> None:
    # Counts are per user and live-only: the owner's soft-deleted rows are not counted.
    owner_refs = accounts.account_references(conn, OWNER_ID, world.owner.account_id)
    assert (owner_refs.transactions, owner_refs.planned, owner_refs.recurring) == (1, 1, 3)
    assert accounts.account_references(conn, OTHER_ID, world.owner.account_id) == (
        AccountReferences(0, 0, 0)
    )


@covers("analytics.bundle")
def _case_analytics(conn: sqlite3.Connection, world: World) -> None:
    assert world.other.category_id not in _analytics_categories(conn, OWNER_ID)
    assert world.owner.category_id not in _analytics_categories(conn, OTHER_ID)


@covers("budget.yearly_grid")
def _case_yearly_grid(conn: sqlite3.Connection, world: World) -> None:
    assert world.other.category_id not in _grid_categories(conn, OWNER_ID)
    assert world.owner.category_id not in _grid_categories(conn, OTHER_ID)


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
            conn,
            OWNER_ID,
            formula(world.other.category_id),
            2026,
            11,
            fx=formula_fx_of(conn, OWNER_ID),
            target_ccy=TARGET_CCY,
        )
    with pytest.raises(recurring_formula.FormulaError):
        recurring_formula.compute_savable_amount(
            conn,
            OTHER_ID,
            formula(world.owner.category_id),
            2026,
            11,
            fx=formula_fx_of(conn, OTHER_ID),
            target_ccy=TARGET_CCY,
        )


@pytest.mark.parametrize("function_id", sorted(COVERED))
def test_user_data_never_crosses_users(
    function_id: str, conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    COVERED[function_id](conn, world_with_tombstones)


def test_soft_deleted_rows_stay_out_of_the_owners_results(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    assert _fortune(conn, OWNER_ID) == OWNER_BALANCE - 1_000
    assert _checked_accounts(conn, OWNER_ID) == {world_with_tombstones.owner.account_id}
    assert _grid_categories(conn, OWNER_ID) == {world_with_tombstones.owner.category_id}


@covers("categories.usage_by_category")
def _case_usage_by_category(conn: sqlite3.Connection, world: World) -> None:
    mine = categories.usage_by_category(conn, OWNER_ID)
    theirs = categories.usage_by_category(conn, OTHER_ID)
    assert world.owner.category_id in mine
    assert world.other.category_id not in mine
    assert world.other.category_id in theirs
    assert world.owner.category_id not in theirs


@covers("categories.entry_count")
def _case_entry_count(conn: sqlite3.Connection, world: World) -> None:
    assert categories.entry_count(conn, OWNER_ID, world.owner.category_id) == 1
    assert categories.entry_count(conn, OWNER_ID, world.other.category_id) == 0
    assert categories.entry_count(conn, OTHER_ID, world.owner.category_id) == 0


@covers("categories.usage_for")
def _case_usage_for(conn: sqlite3.Connection, world: World) -> None:
    mine = categories.usage_for(conn, OWNER_ID, world.owner.category_id)
    assert mine.entry_count == 1
    assert categories.usage_for(conn, OWNER_ID, world.other.category_id).entry_count == 0
    assert categories.usage_for(conn, OTHER_ID, world.owner.category_id).entry_count == 0


@covers("categories.picker_summary")
def _case_picker_summary(conn: sqlite3.Connection, world: World) -> None:
    recent = {c.id for c in categories.picker_summary(conn, OWNER_ID).recent}
    assert world.owner.category_id in recent
    assert world.other.category_id not in recent
    assert all(c.user_id == OWNER_ID for c in categories.picker_summary(conn, OWNER_ID).recent)


def collect() -> list[Violation]:
    """Public service functions with a ``user_id`` parameter that have no isolation case yet."""
    files = {repo_rel(p): p.read_text(encoding="utf-8") for p in src_files("services")}
    missing = []
    for path, name in sorted(public_functions_with_user_id(files)):
        function_id = f"{path.rsplit('/', 1)[-1].removesuffix('.py')}.{name}"
        if function_id not in COVERED:
            missing.append(Violation(path, 0, name, function_id))
    return missing


@pytest.mark.skipif(
    "mutants" in REPO_ROOT.parts,
    reason="mutmut copies src/ with mangled function names (x_<fn>__mutmut_N); the registry scan only holds for the real tree",
)
def test_isolation_registry_matches_allowlist() -> None:
    assert_ratchet("user_isolation", collect(), TEACH)


def test_registry_detects_function_without_an_isolation_case() -> None:
    src = "def list_things(conn, user_id):\n    return []\n\ndef _private(conn, user_id):\n    return 1\n"
    assert public_functions_with_user_id({"services/x.py": src}) == {
        ("services/x.py", "list_things")
    }
