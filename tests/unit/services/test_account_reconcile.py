"""Tests for services.account_reconcile (T-Q266): one transaction for adjustment + snapshot."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.money import parse_amount_minor
from budget_planner.repositories import accounts, audit as audit_repo
from budget_planner.services import account_reconcile, balance, reconciliation
from budget_planner.services.accounts import list_snapshots_for_account

USER_ID = 1
_TODAY = date(2026, 10, 23)


def _account(conn: sqlite3.Connection) -> int:
    new = NewAccount(name="Checking", currency="PLN", opening_balance=100_000)
    return accounts.create(conn, USER_ID, new).id


def test_reconcile_inserts_adjustment_and_snapshot_of_new_balance(conn: sqlite3.Connection) -> None:
    account_id = _account(conn)

    account_reconcile.reconcile_account(
        conn,
        USER_ID,
        account_id=account_id,
        actual_balance_minor=120_000,
        today=_TODAY,
        category_id=None,
        save_snapshot=True,
    )

    assert balance.derive_balance(conn, USER_ID, account_id) == 120_000
    snaps = list_snapshots_for_account(conn, USER_ID, account_id)
    assert [(s.balance, s.note) for s in snaps] == [(120_000, "reconcile snapshot")]
    rows = conn.execute(
        "SELECT amount, description, id FROM transactions WHERE account_id = ? AND user_id = ?",
        (account_id, USER_ID),
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [(20_000, f"auto-reconciliation {_TODAY.isoformat()}")]
    assert len(audit_repo.list_entries(conn, USER_ID, "transaction", rows[0][2])) == 1


def test_zero_delta_is_not_an_error_and_still_snapshots(conn: sqlite3.Connection) -> None:
    account_id = _account(conn)

    account_reconcile.reconcile_account(
        conn,
        USER_ID,
        account_id=account_id,
        actual_balance_minor=100_000,
        today=_TODAY,
        category_id=None,
        save_snapshot=True,
    )

    count = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,)
    ).fetchone()[0]
    assert count == 0
    assert [s.balance for s in list_snapshots_for_account(conn, USER_ID, account_id)] == [100_000]


def test_no_snapshot_unless_requested(conn: sqlite3.Connection) -> None:
    account_id = _account(conn)

    account_reconcile.reconcile_account(
        conn,
        USER_ID,
        account_id=account_id,
        actual_balance_minor=90_000,
        today=_TODAY,
        category_id=None,
        save_snapshot=False,
    )

    assert list_snapshots_for_account(conn, USER_ID, account_id) == []
    assert balance.derive_balance(conn, USER_ID, account_id) == 90_000


def test_failed_reconcile_leaves_no_snapshot(conn: sqlite3.Connection) -> None:
    account_id = _account(conn)

    with pytest.raises(reconciliation.MissingSystemCategoryError):
        account_reconcile.reconcile_account(
            conn,
            USER_ID,
            account_id=account_id,
            actual_balance_minor=90_000,
            today=_TODAY,
            category_id=999_999,
            save_snapshot=True,
        )

    assert list_snapshots_for_account(conn, USER_ID, account_id) == []
    assert balance.derive_balance(conn, USER_ID, account_id) == 100_000


def test_second_users_account_is_not_reconcilable(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    other_account = accounts.create(
        conn, 2, NewAccount(name="Theirs", currency="PLN", opening_balance=5_000)
    ).id

    with pytest.raises(reconciliation.AccountNotFoundError):
        account_reconcile.reconcile_account(
            conn,
            USER_ID,
            account_id=other_account,
            actual_balance_minor=1,
            today=_TODAY,
            category_id=None,
            save_snapshot=True,
        )

    assert list_snapshots_for_account(conn, 2, other_account) == []


def test_target_balance_is_typed_amount_for_a_plain_account(conn: sqlite3.Connection) -> None:
    acc = accounts.find_by_id(conn, USER_ID, _account(conn))
    assert acc is not None

    assert account_reconcile.target_balance_minor(acc, 42_000) == 42_000


def test_target_balance_converts_available_credit_for_a_limited_liability(
    conn: sqlite3.Connection,
) -> None:
    card = accounts.create(
        conn,
        USER_ID,
        NewAccount(
            name="Card",
            currency="PLN",
            opening_balance=0,
            is_liability=True,
            credit_limit_minor=500_000,
        ),
    )

    assert account_reconcile.target_balance_minor(card, 350_000) == -150_000
    with pytest.raises(reconciliation.InvalidAvailableError):
        account_reconcile.target_balance_minor(card, 500_001)


def _live(conn: sqlite3.Connection, *, currency: str = "PLN", opening: int = 120_000) -> int:
    new = NewAccount(name="Prev", currency=currency, opening_balance=opening)
    return accounts.create(conn, USER_ID, new).id


@pytest.mark.parametrize(
    ("actual", "difference", "adjustment"),
    [(125_050, 5_050, "increase"), (120_000, 0, "none"), (118_000, -2_000, "decrease")],
)
def test_preview_difference_is_signed_actual_minus_derived(
    conn: sqlite3.Connection, actual: int, difference: int, adjustment: account_reconcile.Adjustment
) -> None:
    account_id = _live(conn)
    acc = accounts.find_by_id(conn, USER_ID, account_id)
    assert acc is not None
    derived = balance.derive_balance(conn, USER_ID, account_id)

    preview = account_reconcile.preview_difference(acc, actual, derived)

    assert derived == 120_000
    assert preview == account_reconcile.ReconcilePreview(
        entered_minor=actual,
        current_minor=120_000,
        difference_minor=difference,
        target_balance_minor=actual,
        adjustment=adjustment,
    )


def test_preview_difference_for_limited_liability_compares_available_credit(
    conn: sqlite3.Connection,
) -> None:
    new = NewAccount(
        name="Visa",
        currency="PLN",
        is_liability=True,
        credit_limit_minor=500_000,
        opening_balance=-123_456,
    )
    acc = accounts.create(conn, USER_ID, new)

    preview = account_reconcile.preview_difference(acc, 400_000, -123_456)

    assert (preview.current_minor, preview.difference_minor) == (376_544, 23_456)
    assert preview.target_balance_minor == -100_000
    assert preview.adjustment == "increase"
    with pytest.raises(reconciliation.InvalidAvailableError):
        account_reconcile.preview_difference(acc, 500_001, -123_456)


def test_preview_uses_the_account_currency_exponent(conn: sqlite3.Connection) -> None:
    account_id = _live(conn, currency="JPY", opening=120_000)
    acc = accounts.find_by_id(conn, USER_ID, account_id)
    assert acc is not None
    entered = parse_amount_minor("125050", "JPY")
    assert entered == 125_050

    preview = account_reconcile.preview_difference(acc, entered, 120_000)

    assert preview.difference_minor == 5_050
