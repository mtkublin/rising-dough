"""Credit-limit preview: left before and after, edit mode, isolation (T-UR34d, ADR-0134 §2)."""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import accounts, transactions
from budget_planner.services.limit_preview import LimitPreview, compute_limit_preview
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, World

DAY = date(2026, 11, 10)
LIMIT = 500_000


def _card(conn: sqlite3.Connection, *, name: str = "Credit Card") -> int:
    return accounts.create(
        conn,
        OWNER_ID,
        NewAccount(
            name=name,
            currency="PLN",
            opening_balance=0,
            is_liability=True,
            credit_limit_minor=LIMIT,
        ),
    ).id


def _spend(conn: sqlite3.Connection, world: World, card_id: int, amount: int) -> int:
    return transactions.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=DAY,
            category_id=world.owner.category_id,
            account_id=card_id,
            amount=amount,
        ),
    ).id


def test_left_before_and_after_with_exact_minor_units(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    card = _card(conn)
    _spend(conn, world_with_two_users, card, 120_000)
    preview = compute_limit_preview(
        conn,
        OWNER_ID,
        account_id=card,
        category_id=world_with_two_users.owner.category_id,
        amount_raw="500.00",
    )
    assert preview == LimitPreview(
        projected_balance=-170_000,
        available_before=380_000,
        available_after=330_000,
        used_after=170_000,
        limit=LIMIT,
        over_by=0,
        currency="PLN",
        account_name="Credit Card",
    )


def test_a_zero_amount_previews_no_change_and_a_negative_one_nothing(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    """The edit dialog answering a zero amount (handoff edit-transaction--error) keeps its line."""
    card = _card(conn)
    _spend(conn, world_with_two_users, card, 120_000)
    cat = world_with_two_users.owner.category_id
    zero = compute_limit_preview(conn, OWNER_ID, account_id=card, category_id=cat, amount_raw="0")
    assert zero is not None
    assert (zero.available_before, zero.available_after, zero.over_by) == (380_000, 380_000, 0)
    assert (
        compute_limit_preview(conn, OWNER_ID, account_id=card, category_id=cat, amount_raw="-1")
        is None
    )


def test_no_category_previews_only_a_zero_amount(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    """The new-entry 422 for a zero amount with no category keeps its line (handoff, F8)."""
    card = _card(conn)
    _spend(conn, world_with_two_users, card, 120_000)
    zero = compute_limit_preview(
        conn, OWNER_ID, account_id=card, category_id=None, amount_raw="0.00"
    )
    assert zero is not None
    assert (zero.available_before, zero.available_after, zero.over_by) == (380_000, 380_000, 0)
    assert (
        compute_limit_preview(conn, OWNER_ID, account_id=card, category_id=None, amount_raw="5")
        is None
    )


def test_over_limit_reports_exact_over_by_and_zero_left_after(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    card = _card(conn, name="Visa")
    _spend(conn, world_with_two_users, card, 470_000)
    preview = compute_limit_preview(
        conn,
        OWNER_ID,
        account_id=card,
        category_id=world_with_two_users.owner.category_id,
        amount_raw="800.00",
    )
    assert preview is not None
    assert preview.available_before == 30_000
    assert preview.available_after == 0
    assert preview.over_by == 50_000
    assert preview.account_name == "Visa"


def test_edit_mode_excludes_the_edited_transaction_from_before(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    card = _card(conn)
    _spend(conn, world_with_two_users, card, 120_000)
    edited = _spend(conn, world_with_two_users, card, 20_000)
    cat = world_with_two_users.owner.category_id
    plain = compute_limit_preview(
        conn, OWNER_ID, account_id=card, category_id=cat, amount_raw="500.00"
    )
    edit = compute_limit_preview(
        conn,
        OWNER_ID,
        account_id=card,
        category_id=cat,
        amount_raw="500.00",
        exclude_txn_id=edited,
    )
    assert plain is not None
    assert plain.available_before == 360_000
    assert plain.available_after == 310_000
    assert edit is not None
    assert edit.available_before == 380_000
    assert edit.available_after == 330_000
    assert edit.over_by == 0


def test_another_users_transaction_id_changes_nothing(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    card = _card(conn)
    _spend(conn, world_with_two_users, card, 120_000)
    foreign = transactions.create(
        conn,
        OTHER_ID,
        NewTransaction(
            operation_date=DAY,
            category_id=world_with_two_users.other.category_id,
            account_id=world_with_two_users.other.account_id,
            amount=20_000,
        ),
    ).id
    cat = world_with_two_users.owner.category_id
    baseline = compute_limit_preview(
        conn, OWNER_ID, account_id=card, category_id=cat, amount_raw="500.00"
    )
    with_foreign = compute_limit_preview(
        conn,
        OWNER_ID,
        account_id=card,
        category_id=cat,
        amount_raw="500.00",
        exclude_txn_id=foreign,
    )
    assert with_foreign == baseline
    assert with_foreign is not None
    assert with_foreign.available_before == 380_000
