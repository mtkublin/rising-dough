"""Regression tests proving the T-D16 static checker actually bites.

Each case writes a throwaway repository module into ``tmp_path`` and runs
the checker against it, so a silently-broken checker (e.g. one that stops
finding SQL) fails here instead of quietly passing the real sweep.
"""

from __future__ import annotations

import importlib
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.architecture._user_scoping import (
    check_builders_covered,
    check_owned_tables,
    check_paths,
    check_source,
    default_renderers,
)


def _write(tmp_path: Path, body: str) -> Path:
    module = tmp_path / "leaky_repo.py"
    module.write_text(textwrap.dedent(body), encoding="utf-8")
    return module


def test_missing_predicate_in_temp_repo_module_fails(tmp_path: Path) -> None:
    module = _write(
        tmp_path,
        """
        _COLS = "id, name"

        def list_all(conn, user_id):
            return conn.execute(f"SELECT {_COLS} FROM accounts WHERE deleted_at IS NULL")
        """,
    )
    violations = check_paths([module], tmp_path)
    assert len(violations) == 1
    rendered = violations[0].render()
    assert "leaky_repo.py:5" in rendered
    assert "'accounts' lacks user_id" in rendered


def test_scoped_query_passes(tmp_path: Path) -> None:
    module = _write(
        tmp_path,
        """
        def list_all(conn, user_id, include_deleted=False):
            sql = "SELECT id FROM accounts WHERE user_id = ?"
            if not include_deleted:
                sql += " AND deleted_at IS NULL"
            return conn.execute(sql, (user_id,))
        """,
    )
    assert check_paths([module], tmp_path) == []


def test_allowlisted_function_is_skipped(tmp_path: Path) -> None:
    module = _write(
        tmp_path,
        """
        def admin_count(conn):
            return conn.execute("SELECT COUNT(*) FROM accounts")
        """,
    )
    assert check_paths([module], tmp_path, [("leaky_repo.py", "admin_count")]) == []


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        (
            'def f(c, u):\n    c.execute("UPDATE transactions SET amount = ? WHERE id = ?")\n',
            "UPDATE on user-owned table 'transactions'",
        ),
        (
            'def f(c, u):\n    c.execute("DELETE FROM user_preferences WHERE key = ?")\n',
            "DELETE on user-owned table 'user_preferences'",
        ),
        (
            "def f(c, u):\n"
            '    c.execute("INSERT INTO categories(name, direction) VALUES (?, ?)")\n',
            "INSERT into user-owned table 'categories' without user_id",
        ),
        (
            "def f(c, u):\n"
            '    c.execute("SELECT s.id FROM account_snapshots s WHERE s.account_id = ?")\n',
            "lacks a user-scoped reference to 'accounts'",
        ),
        (
            "def f(c, u):\n"
            '    c.execute("INSERT INTO recurring_rule_overrides(rule_id) VALUES (?)")\n',
            "without a user-scoped ownership check on 'recurring_rules'",
        ),
        (
            "def f(c, u):\n"
            '    c.execute("SELECT t.id FROM transactions t JOIN categories c '
            'ON c.id = t.category_id WHERE t.user_id = ?")\n',
            "SELECT on user-owned table 'categories' lacks user_id",
        ),
        (
            "def f(c, u):\n"
            '    c.execute("SELECT id FROM accounts a WHERE a.id IN '
            '(SELECT account_id FROM transactions WHERE user_id = ?)")\n',
            "SELECT on user-owned table 'accounts' lacks user_id",
        ),
    ],
)
def test_each_rule_reports_violation(source: str, fragment: str) -> None:
    violations = check_source(source, "mod.py")
    assert any(fragment in v.message for v in violations), [v.message for v in violations]


@pytest.mark.parametrize(
    "source",
    [
        # FK-scoped via JOIN + EXISTS subquery.
        "def f(c, u):\n"
        '    c.execute("SELECT s.id FROM account_snapshots s JOIN accounts a '
        'ON a.id = s.account_id WHERE a.user_id = ?")\n',
        "def f(c, u):\n"
        '    c.execute("DELETE FROM recurring_rule_overrides AS o WHERE o.id = ? AND EXISTS '
        '(SELECT 1 FROM recurring_rules r WHERE r.id = o.rule_id AND r.user_id = ?)")\n',
        # FK-scoped insert preceded by an ownership check in the same function.
        "def f(c, u):\n"
        '    c.execute("SELECT 1 FROM accounts WHERE id = ? AND user_id = ?")\n'
        '    c.execute("INSERT INTO account_snapshots(account_id, balance) VALUES (?, ?)")\n',
        # Clause list assembled with append / insert + join.
        "def f(c, u, flt):\n"
        "    clauses, params = helper(flt)\n"
        '    clauses.insert(0, "t.user_id = ?")\n'
        '    sql = "SELECT t.id FROM transactions t WHERE " + " AND ".join(clauses)\n'
        "    c.execute(sql, params)\n",
        # Credential tables may be keyed by their opaque id.
        'def f(c, sid):\n    c.execute("SELECT user_id FROM sessions WHERE id = ?")\n',
        # Non-user-owned tables are ignored.
        'def f(c):\n    c.execute("SELECT rate FROM fx_rates WHERE date = ?")\n',
    ],
)
def test_compliant_patterns_pass(source: str) -> None:
    assert check_source(source, "mod.py") == []


def test_unparseable_sql_is_reported() -> None:
    violations = check_source('def f(c):\n    c.execute("SELEC id FROM accounts")\n', "mod.py")
    assert violations
    assert "unparseable SQL" in violations[0].message


_SPEC_MODULE = """
_COLS = "id, name"

ACCT = OwnedTable[int](
    table="accounts", entity_type="account", columns=_COLS, hydrate=int, order_by="id ASC"
)
"""


def _shared_with(**overrides: object) -> object:
    real = importlib.import_module("budget_planner.repositories._shared")
    return SimpleNamespace(**{**vars(real), **overrides})


def test_owned_spec_resolves_and_real_builders_pass(tmp_path: Path) -> None:
    module = _write(tmp_path, _SPEC_MODULE)
    assert check_owned_tables([module], tmp_path) == []


def test_owned_builder_dropping_user_id_fails_naming_table(tmp_path: Path) -> None:
    def leaky(table: str, columns: str, keys: object, *, include_deleted: bool) -> str:
        return "SELECT id FROM TABLE WHERE id = ?".replace("TABLE", table)

    module = _write(tmp_path, _SPEC_MODULE)
    renderers = default_renderers(_shared_with(find_sql=leaky))
    violations = check_owned_tables([module], tmp_path, renderers)
    assert violations
    assert all(v.function == "find_sql" for v in violations)
    assert "table 'accounts'" in violations[0].message
    assert "lacks user_id" in violations[0].message


def test_owned_insert_builder_without_user_id_fails(tmp_path: Path) -> None:
    module = _write(tmp_path, _SPEC_MODULE)
    renderers = default_renderers(
        _shared_with(
            insert_sql=lambda table, _keys: "INSERT INTO TABLE(name) VALUES (?)".replace(
                "TABLE", table
            )
        )
    )
    violations = check_owned_tables([module], tmp_path, renderers)
    assert [v.function for v in violations] == ["insert_sql"]
    assert "without user_id column" in violations[0].message


def test_owned_spec_with_unknown_table_fails(tmp_path: Path) -> None:
    module = _write(tmp_path, _SPEC_MODULE.replace('"accounts"', '"fx_rates"'))
    violations = check_owned_tables([module], tmp_path)
    assert len(violations) == 1
    assert "unknown table 'fx_rates'" in violations[0].message


def test_owned_spec_with_unresolvable_table_fails(tmp_path: Path) -> None:
    module = _write(tmp_path, _SPEC_MODULE.replace('"accounts"', "make_table()"))
    violations = check_owned_tables([module], tmp_path)
    assert [v.message for v in violations] == ["spec is not statically resolvable"]


def test_dynamic_table_statement_is_not_silently_skipped(tmp_path: Path) -> None:
    module = _write(
        tmp_path,
        """
        def raw(conn, spec, user_id):
            return conn.execute(f"SELECT id FROM {spec.table} WHERE id = ?", (1,))
        """,
    )
    violations = check_paths([module], tmp_path)
    assert len(violations) == 1
    assert "dynamic table name is not resolvable" in violations[0].message


def test_builder_without_renderer_is_reported() -> None:
    source = "def new_sql(table):\n    return ''\n"
    problems = check_builders_covered(source, default_renderers())
    assert "SQL builder 'new_sql' has no guard renderer" in problems
