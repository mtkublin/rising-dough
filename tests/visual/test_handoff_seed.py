"""Spot checks of the handoff base seed (T-UR00b, ADR-0147 §3).

Figures come from the real services over the seeded scratch DB; the expected
values are the handoff's own (value-inventory section 2). Where the app's
service rules disagree with the handoff board, the test pins the service's
value and the comment names the overlay row (value-inventory section 5).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
    users as users_repo,
)
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
    budget as budget_service,
    fortune as fortune_service,
    fx as fx_service,
    invites as invites_service,
    security_settings,
    today as today_service,
)
from tests.visual import handoff_seed as seed
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE

USER = seed.OWNER_ID
DAY = dt.date.fromisoformat(HANDOFF_FIXTURE_DATE)
NOW = dt.datetime(2026, 10, 31, 10, tzinfo=dt.UTC)
TZ = "Europe/Warsaw"
Built = tuple[sqlite3.Connection, seed.SeedResult]


def _open(path: Path) -> sqlite3.Connection:
    return get_connection(Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}"))


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Built]:
    result = seed.build_seed(tmp_path_factory.mktemp("seed") / "base.sqlite")
    conn = _open(result.db_path)
    try:
        yield conn, result
    finally:
        conn.close()


def _built(tmp_path: Path, *modifiers: str) -> sqlite3.Connection:
    return _open(seed.build_seed(tmp_path / "m.sqlite", modifiers=modifiers).db_path)


def test_entity_counts() -> None:
    assert (len(seed.ACCOUNTS), len(seed.CATEGORIES)) == (10, 22)
    assert len(seed.TRANSACTIONS) == 26
    assert (len(seed.PLANNED), len(seed.RULES), len(seed.BUDGETS)) == (4, 15, 13)


def test_refuses_existing_db(tmp_path: Path) -> None:
    path = tmp_path / "x.sqlite"
    path.write_bytes(b"")
    with pytest.raises(FileExistsError):
        seed.build_seed(path)


def test_accounts_balances(base: Built) -> None:
    conn, _ = base
    accounts = accounts_repo.list_all(conn, USER)
    balances = balance_service.derive_balances(conn, USER, accounts)
    by_name = {a.name: balances[a.id] for a in accounts}
    assert by_name == {
        "Investments A": 1_699_129,
        "Savings": 1_245_304,
        "Investments C": 572_922,
        "Checking": 368_581,
        "Investments B": 238_368,
        "Investments D": 228_746,
        "Cash Wallet": 8_594,
        "Checking EUR": -660_115,
        "Credit Card": -245_574,
        "Everyday Spending": -11_986,
    }
    card = next(a for a in accounts if a.name == "Credit Card")
    assert (card.is_liability, card.credit_limit_minor) == (True, 1_497_737)
    assert 1_497_737 + by_name["Credit Card"] == 1_252_163  # "available 12,521.63 of 14,977.37"


def test_net_worth(base: Built) -> None:
    conn, _ = base
    totals = fortune_service.compute_fortune(
        conn, USER, fx_service.converter_for(conn, Settings(_env_file=None), DAY)
    )
    assert (totals.net_base, totals.assets_base, totals.liabilities_base) == (
        3_443_969,
        3_689_543,
        245_574,
    )


def test_last_checked_dates(base: Built) -> None:
    conn, _ = base
    rows = accounts_service.last_checked(conn, USER)
    names = {a.id: a.name for a in accounts_repo.list_all(conn, USER)}
    checked = {
        names[r.account_id]: r.last_checked_at.date().isoformat() for r in rows if r.last_checked_at
    }
    assert checked["Checking"] == "2026-04-01"
    # Reconciliation rows on 29 Oct count as a check: the handoff's "checked 01 JUL" for
    # Investments C and "01 APR" for Cash Wallet cannot be produced (overlay).
    assert checked["Investments C"] == "2026-10-29"
    assert checked["Cash Wallet"] == "2026-10-29"
    assert checked["Everyday Spending"] == "2026-09-01"


def test_categories_and_deleted(base: Built) -> None:
    conn, _ = base
    live = categories_repo.list_all(conn, USER)
    by_direction: dict[Direction, int] = {}
    for c in live:
        by_direction[c.direction] = by_direction.get(c.direction, 0) + 1
    assert by_direction[Direction.EXPENSE] == 17
    assert by_direction[Direction.INCOME] == 5
    # ADR-0151: the picker's N excludes Reconciliation (system-only): 17 + 5 + Transit.
    assert len([c for c in live if c.name != "Reconciliation"]) == 23
    deleted = categories_repo.list_recently_deleted(conn, USER)
    stamps = {c.name: c.deleted_at for c in deleted}
    assert sorted(stamps) == ["Bank Fees", "Opłaty bankowe i prowizje", "VAT Refund #6"]
    assert stamps["VAT Refund #6"] == dt.datetime(2026, 10, 29, 19, 6, tzinfo=dt.UTC)


def test_ledger_rows(base: Built) -> None:
    conn, _ = base
    rows = transactions_repo.list_filtered(conn, USER, TransactionFilter())
    assert len(rows) == 26  # tab count 616 is a handoff-only figure: overlay
    newest = max(rows, key=lambda t: (t.operation_date, t.id))
    assert (newest.operation_date, newest.amount, newest.description) == (
        dt.date(2026, 10, 31),
        3_550,
        "Takeaway",
    )
    assert sorted(t.amount for t in rows if t.description == "Reconciliation") == [-1_472, 957]
    transit = next(t for t in rows if t.dest_account_id is not None)
    assert (transit.amount, transit.operation_date) == (2_193, dt.date(2026, 10, 26))


def test_budget_and_today(base: Built) -> None:
    conn, _ = base
    year, month = budget_service.fiscal_month_for(conn, USER, DAY)
    summary = budget_service.month_summary(
        conn, USER, year, month, today=DAY, base_currency="PLN", display_timezone=TZ
    )
    assert (summary.period_start, summary.next_income_date) == (
        dt.date(2026, 10, 7),
        dt.date(2026, 11, 7),
    )
    assert summary.days_until_next_income == 7
    assert summary.anchor_category_name == "Salary"
    totals = summary.totals
    assert (totals.budgeted_minor, totals.spent_minor) == (644_908, 501_455)
    assert totals.unbudgeted_committed_minor == 27_794
    # The handoff prints committed 34.60 / left 1,399.93 / 199.99 per day. The app also
    # commits the overdue planned "Annual insurance" (412.00, dated 28 Oct, inside the
    # period): committed 446.60, left 987.93, 141.13 per day. Overlay rows (section 5).
    assert (totals.committed_minor, totals.remaining_minor) == (44_660, 98_793)
    assert summary.left_daily_spend_minor == 14_113
    lines = {line.category_name: line for line in summary.lines}
    assert lines["Big Purchases"].spent_minor == 23_482
    assert lines["Big Purchases"].budgeted_minor == 60_435
    assert lines["Nights Out"].spent_minor == 160_037
    assert lines["Takeaway"].budgeted_minor == 39_427


def test_afford_figures(base: Built) -> None:
    conn, _ = base
    small = today_service.afford(conn, USER, DAY, 25_000, base_currency="PLN", display_timezone=TZ)
    assert (small.per_day_minor, small.delta_minor) == (10_542, -3_571)  # delta matches 35.71
    over = today_service.afford(conn, USER, DAY, 180_000, base_currency="PLN", display_timezone=TZ)
    # Handoff: -57.15 / 400.07 over (ADR-0151) on left 1,399.93; here left is 987.93.
    assert (over.unclamped_per_day_minor, over.over_minor) == (-11_601, 81_207)


def test_planned_and_recurring(base: Built) -> None:
    conn, _ = base
    planned = planned_repo.list_filtered(conn, USER, PlannedFilter())
    assert sorted((p.operation_date.isoformat(), p.amount, p.description) for p in planned) == [
        ("2026-10-28", 41_200, "Annual insurance"),
        ("2026-10-31", 112_045, "Tax refund"),
        ("2026-12-15", 223_980, "Car"),
    ]
    deleted = planned_repo.list_recently_deleted(conn, USER)
    assert [(p.amount, p.deleted_at) for p in deleted] == [
        (230_635, dt.datetime(2026, 10, 29, 19, 30, tzinfo=dt.UTC))
    ]
    rules = recurring_repo.list_rules(conn, USER)
    assert len(rules) == 15  # handoff says 27 rules; it lists 12 + 3 on Today: overlay
    assert min(r.next_due for r in rules) == dt.date(2026, 11, 1)
    formulas = sorted(r.default_description for r in rules if r.amount_formula is not None)
    assert formulas == ["Salary", "Taxes", "Transit", "VAT Refund"]
    overrides = [o for r in rules for o in recurring_repo.list_overrides_all(conn, USER, r.id)]
    assert sorted(o.amount_override or 0 for o in overrides) == [
        164_000,
        195_000,
        195_000,
        1_580_000,
        1_595_000,
        1_610_000,
        1_650_000,
    ]


def test_users_invite_and_login(base: Built) -> None:
    conn, result = base
    listing = {u.email: u for u in users_repo.list_live(conn)}
    assert sorted(str(e) for e in listing) == [
        "owner@example.test",
        "parent@example.test",
        "partner@example.test",
    ]
    assert listing["owner@example.test"].is_admin
    assert listing["parent@example.test"].must_change_password
    assert listing["partner@example.test"].name == "Ola"
    assert listing["partner@example.test"].last_seen_at == dt.datetime(
        2026, 10, 30, 20, 12, tzinfo=dt.UTC
    )
    assert invites_service.link_state(conn, result.invite_token or "", now=NOW) == "pending"
    assert result.session_token


def test_unknown_modifier_raises() -> None:
    with pytest.raises(ValueError, match="unknown seed modifier"):
        seed.apply_modifiers(seed.BASE, ["nope"])


def test_modifiers_are_pure() -> None:
    before = seed.BASE
    assert seed.apply_modifiers(before, ["empty"]) != before
    assert before == seed.BASE
    assert seed.apply_modifiers(before, ["no-matches", "over-limit", "form-error"]) == before


@pytest.mark.parametrize("name", seed.MODIFIER_NAMES)
def test_every_modifier_builds(name: str, tmp_path: Path) -> None:
    _built(tmp_path, name).close()


def test_empty_accounts(tmp_path: Path) -> None:
    conn = _built(tmp_path, "empty-accounts")
    assert accounts_repo.list_all(conn, USER) == []
    assert transactions_repo.list_filtered(conn, USER, TransactionFilter()) == []
    conn.close()


def test_empty_ledger_planned_recurring(tmp_path: Path) -> None:
    conn = _built(tmp_path, "empty-ledger", "empty-planned", "empty-recurring")
    assert transactions_repo.list_filtered(conn, USER, TransactionFilter()) == []
    assert planned_repo.list_filtered(conn, USER, PlannedFilter()) == []
    assert recurring_repo.list_rules(conn, USER) == []
    assert len(accounts_repo.list_all(conn, USER)) == 10
    conn.close()


def test_long_adds_stress_rows(tmp_path: Path) -> None:
    conn = _built(tmp_path, "long")
    rows = transactions_repo.list_filtered(conn, USER, TransactionFilter())
    assert max(t.amount for t in rows) == 123_456_789
    assert max(len(t.description) for t in rows) == len(seed.LONG_DESCRIPTION)
    conn.close()


def test_invite_expired(tmp_path: Path) -> None:
    result = seed.build_seed(tmp_path / "e.sqlite", modifiers=("invite-expired",))
    conn = _open(result.db_path)
    state = invites_service.link_state(conn, result.invite_token or "", now=NOW)
    conn.close()
    assert state == "expired"


def test_invite_used(tmp_path: Path) -> None:
    result = seed.build_seed(tmp_path / "u.sqlite", modifiers=("invite-used",))
    conn = _open(result.db_path)
    state = invites_service.link_state(conn, result.invite_token or "", now=NOW)
    emails = sorted(str(u.email) for u in users_repo.list_live(conn))
    conn.close()
    assert state == "used"
    assert "accountant@example.test" in emails


def test_recurring_board_keeps_the_twelve_listed_rules(tmp_path: Path) -> None:
    """ledger/recurring.html lists 12 rules; the base also holds Today's 3 (15)."""
    conn = _built(tmp_path, "recurring-board")
    rules = recurring_repo.list_rules(conn, USER, active_only=True)
    conn.close()
    assert len(rules) == 12
    assert sorted(
        (r.default_description, r.next_due.isoformat(), r.default_amount) for r in rules
    ) == [
        ("Car", "2027-03-10", 405_682),
        ("Car insurance", "2027-01-15", 41_200),
        ("Fixed Costs", "2026-11-01", 27_794),
        ("Fixed Costs", "2026-11-15", 212_639),
        ("Rent", "2026-11-18", 190_000),
        ("Salary", "2026-11-07", 1_621_397),
        ("Salary", "2027-03-07", 3_053_619),
        ("Subscriptions", "2026-11-01", 1_131),
        ("Subscriptions", "2026-11-05", 2_329),
        ("Taxes", "2026-11-12", 183_693),
        ("Transit", "2026-11-12", 1_241_580),
        ("VAT Refund", "2026-11-07", 372_921),
    ]


def test_owner_has_the_firefox_and_the_safari_session(base: Built) -> None:
    """settings/security.html lists two owner sessions: this device and Safari on iPhone."""
    conn, result = base
    with clock.frozen(NOW):
        view = security_settings.security_view(
            conn, USER, session_token=result.session_token, absolute_lifetime_days=30
        )
    assert [(r.device_label, r.is_current, r.session.ip) for r in view.session_rows] == [
        ("Firefox \u00b7 macOS", True, "83.24.117.9"),
        ("Safari \u00b7 iPhone", False, "83.24.117.21"),
    ]
    phone = view.session_rows[1]
    assert phone.session.created_at == dt.datetime(2026, 10, 26, 17, 40, tzinfo=dt.UTC)
    assert phone.session.last_seen_at == dt.datetime(2026, 10, 30, 21, 3, tzinfo=dt.UTC)
    assert phone.absolute_expires_at == dt.datetime(2026, 11, 25, 17, 40, tzinfo=dt.UTC)
