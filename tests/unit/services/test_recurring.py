"""Tests for the recurring occurrence generator (T-022) + promotion (T-118)."""

from __future__ import annotations

import datetime as _dt_module
import logging
import sqlite3
from datetime import UTC, date, datetime

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    audit as audit_repo,
    categories as categories_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import recurring as rec_svc
from budget_planner.services._promotion import UnsupportedDirectionError, ValidationError

USER_ID = 1

_UTC = UTC


def _rule(
    *,
    rule_id: int = 1,
    cadence: Cadence = Cadence.MONTHLY,
    start_date: date = date(2026, 1, 15),
    end_date: date | None = None,
    day_of_month: int | None = None,
    month_of_year: int | None = None,
    active: bool = True,
    amount: int = 10_000,
    description: str = "rent",
) -> RecurringRule:
    return RecurringRule(
        id=rule_id,
        user_id=1,
        cadence=cadence,
        start_date=start_date,
        end_date=end_date,
        category_id=10,
        account_id=1,
        dest_account_id=None,
        default_amount=amount,
        default_description=description,
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        active=active,
        next_due=start_date,
        last_promoted_date=None,
        created_at=datetime(2026, 1, 1, tzinfo=_UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=_UTC),
        deleted_at=None,
    )


def _override(
    *,
    override_id: int = 100,
    rule_id: int = 1,
    occurrence_date: date,
    state: OverrideState = OverrideState.SKIPPED,
    amount_override: int | None = None,
    description_override: str | None = None,
    date_override: date | None = None,
) -> RecurringOverride:
    return RecurringOverride(
        id=override_id,
        rule_id=rule_id,
        occurrence_date=occurrence_date,
        state=state,
        amount_override=amount_override,
        description_override=description_override,
        date_override=date_override,
        created_at=datetime(2026, 1, 1, tzinfo=_UTC),
    )


# ---------------------------------------------------------------------------
# cadence happy paths
# ---------------------------------------------------------------------------
def test_monthly_mid_month() -> None:
    rule = _rule(start_date=date(2026, 3, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 3, 1), date(2026, 6, 30))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 3, 15),
        date(2026, 4, 15),
        date(2026, 5, 15),
        date(2026, 6, 15),
    ]


def test_monthly_end_of_month_clamp() -> None:
    rule = _rule(start_date=date(2026, 1, 31))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 4, 30))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]


def test_monthly_leap_year() -> None:
    rule = _rule(start_date=date(2024, 1, 31))
    occs = rec_svc.generate_occurrences(rule, date(2024, 1, 1), date(2024, 4, 30))
    assert [o.occurrence_date for o in occs] == [
        date(2024, 1, 31),
        date(2024, 2, 29),
        date(2024, 3, 31),
        date(2024, 4, 30),
    ]


def test_quarterly() -> None:
    rule = _rule(cadence=Cadence.QUARTERLY, start_date=date(2026, 2, 10))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2027, 1, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 2, 10),
        date(2026, 5, 10),
        date(2026, 8, 10),
        date(2026, 11, 10),
    ]


def test_quarterly_year_boundary() -> None:
    rule = _rule(cadence=Cadence.QUARTERLY, start_date=date(2026, 11, 20))
    occs = rec_svc.generate_occurrences(rule, date(2026, 10, 1), date(2027, 3, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 11, 20),
        date(2027, 2, 20),
    ]


def test_yearly() -> None:
    rule = _rule(cadence=Cadence.YEARLY, start_date=date(2024, 7, 4))
    occs = rec_svc.generate_occurrences(rule, date(2024, 1, 1), date(2027, 12, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2024, 7, 4),
        date(2025, 7, 4),
        date(2026, 7, 4),
        date(2027, 7, 4),
    ]


def test_yearly_feb_29() -> None:
    rule = _rule(cadence=Cadence.YEARLY, start_date=date(2024, 2, 29))
    occs = rec_svc.generate_occurrences(rule, date(2024, 1, 1), date(2028, 12, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2024, 2, 29),
        date(2025, 2, 28),
        date(2026, 2, 28),
        date(2027, 2, 28),
        date(2028, 2, 29),
    ]


def test_yearly_month_of_year_before_start_month_rolls_year() -> None:
    """Yearly rule starting mid-year with month_of_year in an earlier month
    should produce the next-year occurrence first (ADR-0013 handoff note)."""
    rule = _rule(
        cadence=Cadence.YEARLY,
        start_date=date(2026, 6, 1),
        month_of_year=3,  # March — earlier than June
        day_of_month=15,
    )
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2029, 12, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2027, 3, 15),
        date(2028, 3, 15),
        date(2029, 3, 15),
    ]


def test_yearly_with_month_of_year_override() -> None:
    rule = _rule(
        cadence=Cadence.YEARLY,
        start_date=date(2024, 1, 1),
        month_of_year=12,
        day_of_month=24,
    )
    occs = rec_svc.generate_occurrences(rule, date(2024, 1, 1), date(2027, 12, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2024, 12, 24),
        date(2025, 12, 24),
        date(2026, 12, 24),
        date(2027, 12, 24),
    ]


# ---------------------------------------------------------------------------
# range / lifecycle
# ---------------------------------------------------------------------------
def test_range_start_before_rule_start() -> None:
    rule = _rule(start_date=date(2026, 3, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 4, 30))
    assert [o.occurrence_date for o in occs] == [date(2026, 3, 15), date(2026, 4, 15)]


def test_range_end_after_rule_end() -> None:
    rule = _rule(start_date=date(2026, 1, 15), end_date=date(2026, 3, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 6, 30))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_empty_intersection() -> None:
    rule = _rule(start_date=date(2026, 7, 1))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 3, 1))
    assert occs == ()


def test_inactive_rule_returns_empty() -> None:
    rule = _rule(active=False)
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 12, 31))
    assert occs == ()


# ---------------------------------------------------------------------------
# apply_overrides state machine
# ---------------------------------------------------------------------------
def test_skip_single() -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 4, 30))
    overrides = [_override(occurrence_date=date(2026, 2, 15))]
    out = rec_svc.apply_overrides(occs, overrides)
    assert [o.occurrence_date for o in out] == [
        date(2026, 1, 15),
        date(2026, 3, 15),
        date(2026, 4, 15),
    ]
    assert all(not o.is_skipped for o in out)


def test_override_amount_only() -> None:
    rule = _rule(start_date=date(2026, 1, 15), amount=10_000)
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    overrides = [
        _override(
            occurrence_date=date(2026, 2, 15),
            state=OverrideState.OVERRIDDEN,
            amount_override=20_000,
        )
    ]
    out = rec_svc.apply_overrides(occs, overrides)
    feb = next(o for o in out if o.occurrence_date == date(2026, 2, 15))
    assert feb.amount == 20_000
    assert feb.is_overridden
    jan = next(o for o in out if o.occurrence_date == date(2026, 1, 15))
    assert jan.amount == 10_000
    assert not jan.is_overridden


def test_override_description_only() -> None:
    rule = _rule(start_date=date(2026, 1, 15), description="rent")
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 2, 28))
    overrides = [
        _override(
            occurrence_date=date(2026, 2, 15),
            state=OverrideState.OVERRIDDEN,
            description_override="rent +utilities",
        )
    ]
    out = rec_svc.apply_overrides(occs, overrides)
    feb = next(o for o in out if o.occurrence_date == date(2026, 2, 15))
    assert feb.description == "rent +utilities"
    assert feb.amount == 10_000  # unchanged


def test_override_date_shifts_effective_date() -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 4, 30))
    overrides = [
        _override(
            occurrence_date=date(2026, 2, 15),  # canonical key
            state=OverrideState.OVERRIDDEN,
            date_override=date(2026, 2, 25),
        )
    ]
    out = rec_svc.apply_overrides(occs, overrides)
    # Overridden occurrence keeps canonical occurrence_date but effective_date shifts.
    feb = next(o for o in out if o.occurrence_date == date(2026, 2, 15))
    assert feb.effective_date == date(2026, 2, 25)
    assert feb.is_overridden


def test_orphan_override_dropped(caplog: pytest.LogCaptureFixture) -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 2, 28))
    overrides = [
        _override(occurrence_date=date(2026, 5, 15))  # not in canonical schedule
    ]
    with caplog.at_level(logging.DEBUG, logger="budget_planner.services.recurring"):
        out = rec_svc.apply_overrides(occs, overrides)
    assert len(out) == len(occs)  # orphan silently dropped
    assert any("orphan" in r.message.lower() for r in caplog.records)


def test_no_overrides_passthrough() -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    out = rec_svc.apply_overrides(occs, [])
    assert out == occs


def test_expand_composes() -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    overrides = [_override(occurrence_date=date(2026, 2, 15))]
    out = rec_svc.expand(rule, overrides, date(2026, 1, 1), date(2026, 3, 31))
    assert [o.occurrence_date for o in out] == [date(2026, 1, 15), date(2026, 3, 15)]


def test_expand_empty_overrides_matches_generate() -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    expand_out = rec_svc.expand(rule, [], date(2026, 1, 1), date(2026, 4, 30))
    gen_out = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 4, 30))
    assert expand_out == gen_out


def test_date_override_sort_order() -> None:
    # May override shifts to July — should sort after June canonical.
    rule = _rule(start_date=date(2026, 1, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 7, 31))
    overrides = [
        _override(
            occurrence_date=date(2026, 5, 15),
            state=OverrideState.OVERRIDDEN,
            date_override=date(2026, 7, 20),
        )
    ]
    out = rec_svc.apply_overrides(occs, overrides)
    effective_dates = [o.effective_date for o in out]
    assert effective_dates == sorted(effective_dates)
    assert date(2026, 7, 20) in effective_dates


def test_duplicate_override_warns_last_wins(caplog: pytest.LogCaptureFixture) -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    overrides = [
        _override(
            override_id=1,
            occurrence_date=date(2026, 2, 15),
            state=OverrideState.OVERRIDDEN,
            amount_override=20_000,
        ),
        _override(
            override_id=2,
            occurrence_date=date(2026, 2, 15),
            state=OverrideState.OVERRIDDEN,
            amount_override=30_000,
        ),
    ]
    with caplog.at_level(logging.WARNING, logger="budget_planner.services.recurring"):
        out = rec_svc.apply_overrides(occs, overrides)
    feb = next(o for o in out if o.occurrence_date == date(2026, 2, 15))
    assert feb.amount == 30_000
    assert any("collide" in r.message.lower() for r in caplog.records)


def test_partition_invariant() -> None:
    """Occurrences in [a, b] + (b, c] equal [a, c] with same rule."""
    rule = _rule(start_date=date(2026, 1, 15))
    a_to_b = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    b1_to_c = rec_svc.generate_occurrences(rule, date(2026, 4, 1), date(2026, 7, 31))
    full = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 7, 31))
    assert a_to_b + b1_to_c == full


# ---------------------------------------------------------------------------
# T-118: advance_next_due (pure)
# ---------------------------------------------------------------------------
def test_advance_next_due_monthly() -> None:
    out = rec_svc.advance_next_due(Cadence.MONTHLY, date(2026, 3, 15), None, None, None)
    assert out == date(2026, 4, 15)


def test_advance_next_due_quarterly() -> None:
    out = rec_svc.advance_next_due(Cadence.QUARTERLY, date(2026, 2, 10), None, None, None)
    assert out == date(2026, 5, 10)


def test_advance_next_due_yearly() -> None:
    out = rec_svc.advance_next_due(Cadence.YEARLY, date(2026, 7, 4), None, None, None)
    assert out == date(2027, 7, 4)


def test_advance_next_due_eom_clamp_31_to_feb_28() -> None:
    out = rec_svc.advance_next_due(Cadence.MONTHLY, date(2026, 1, 31), None, 31, None)
    assert out == date(2026, 2, 28)


def test_advance_next_due_eom_clamp_31_to_leap_feb_29() -> None:
    out = rec_svc.advance_next_due(Cadence.MONTHLY, date(2024, 1, 31), None, 31, None)
    assert out == date(2024, 2, 29)


def test_advance_next_due_feb_29_leap_boundary() -> None:
    # Feb 29 2024 → Feb 28 2025 (non-leap recovery to 28).
    out = rec_svc.advance_next_due(Cadence.YEARLY, date(2024, 2, 29), None, 29, 2)
    assert out == date(2025, 2, 28)


def test_advance_next_due_feb_28_recovers_to_feb_29() -> None:
    # Feb 28 2025 anchor_day=29 → next leap year lands Feb 29 2026? Actually 2026 is non-leap.
    # Walk until the next leap year: 2025 → 2026 (28), 2026→2027 (28), 2027→2028 (29).
    cur: date | None = date(2025, 2, 28)
    for _ in range(4):
        cur = rec_svc.advance_next_due(Cadence.YEARLY, cur, None, 29, 2)  # type: ignore[arg-type]
    # 2025 → 2026 → 2027 → 2028 → 2029
    assert cur == date(2029, 2, 28)


def test_advance_next_due_end_date_boundary_returns_none() -> None:
    out = rec_svc.advance_next_due(
        Cadence.MONTHLY, date(2026, 3, 15), date(2026, 3, 20), None, None
    )
    assert out is None


def test_advance_next_due_at_end_date_inclusive() -> None:
    # end_date exactly on the next step → that step is still valid.
    out = rec_svc.advance_next_due(
        Cadence.MONTHLY, date(2026, 3, 15), date(2026, 4, 15), None, None
    )
    assert out == date(2026, 4, 15)


# ---------------------------------------------------------------------------
# T-118: first_due_on_or_after (pure)
# ---------------------------------------------------------------------------
def test_first_due_future_rule_returns_start_date() -> None:
    rule = _rule(start_date=date(2027, 6, 1))
    assert rec_svc.first_due_on_or_after(rule, today=date(2026, 1, 1)) == date(2027, 6, 1)


def test_first_due_past_rule_returns_next_upcoming() -> None:
    rule = _rule(start_date=date(2024, 1, 15))
    out = rec_svc.first_due_on_or_after(rule, today=date(2026, 4, 2))
    # Monthly on day 15 → next upcoming >= 2026-04-02 is 2026-04-15.
    assert out == date(2026, 4, 15)


def test_first_due_terminal_rule_returns_start_sentinel() -> None:
    rule = _rule(start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    # today after end_date → no occurrences; sentinel = start_date.
    assert rec_svc.first_due_on_or_after(rule, today=date(2026, 1, 1)) == date(2024, 1, 1)


# occurrence_in_month helper tests
def test_occurrence_in_month_monthly_rule_hits_target_day() -> None:
    rule = _rule(start_date=date(2026, 1, 15))
    assert rec_svc.occurrence_in_month(rule, 2026, 7) == date(2026, 7, 15)


def test_occurrence_in_month_month_without_occurrence_returns_none() -> None:
    rule = _rule(cadence=Cadence.YEARLY, start_date=date(2026, 3, 10))
    assert rec_svc.occurrence_in_month(rule, 2026, 7) is None
    assert rec_svc.occurrence_in_month(rule, 2027, 3) == date(2027, 3, 10)


def test_occurrence_in_month_december_boundary() -> None:
    rule = _rule(start_date=date(2026, 1, 31))
    # Dec has 31 days, so monthly on day 31 → 2026-12-31.
    assert rec_svc.occurrence_in_month(rule, 2026, 12) == date(2026, 12, 31)


# ---------------------------------------------------------------------------
# T-118: promote_recurring + skip_and_advance (DB-backed)
# ---------------------------------------------------------------------------
@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    """Seed accounts + categories + a monthly rent rule starting next_due = today+."""
    checking = accounts_repo.create(conn, USER_ID, NewAccount(name="Checking", currency="PLN")).id
    savings = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN")).id
    eur = accounts_repo.create(conn, USER_ID, NewAccount(name="EUR", currency="EUR")).id
    rent = categories_repo.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    transit = categories_repo.find_by_name(conn, USER_ID, "Transit")
    reconciliation = categories_repo.find_by_name(conn, USER_ID, "Reconciliation")
    assert transit is not None and reconciliation is not None
    rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            category_id=rent,
            account_id=checking,
            default_amount=200_000,
            default_description="rent",
        ),
    )
    return {
        "checking": checking,
        "savings": savings,
        "eur": eur,
        "rent": rent,
        "transit": transit.id,
        "reconciliation": reconciliation.id,
        "rule": rule.id,
    }


def test_promote_happy_path_advances_next_due(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule_id = world["rule"]
    before = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert before is not None
    due = before.next_due
    txn = rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    assert txn.promoted_from_recurring_rule_id == rule_id
    assert txn.promoted_from_recurring_date == due
    assert txn.amount == 200_000
    assert txn.operation_date == due

    after = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert after is not None
    assert after.next_due > due
    assert after.last_promoted_date == due


def test_promote_overridden_amount_merges(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rule_id = world["rule"]
    rule = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert rule is not None
    recurring_repo.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_id,
            occurrence_date=rule.next_due,
            state=OverrideState.OVERRIDDEN,
            amount_override=250_000,
            description_override="rent + utilities",
        ),
    )
    txn = rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    assert txn.amount == 250_000
    assert txn.description == "rent + utilities"
    # ADR-0046: default list hides consumed; history retains it.
    assert recurring_repo.list_overrides(conn, USER_ID, rule_id) == []
    historical = recurring_repo.list_overrides_all(conn, USER_ID, rule_id)
    assert len(historical) == 1
    assert historical[0].promoted_to_txn_id == txn.id


def test_promote_skipped_blocks(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rule_id = world["rule"]
    rule = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert rule is not None
    recurring_repo.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_id,
            occurrence_date=rule.next_due,
            state=OverrideState.SKIPPED,
        ),
    )
    with pytest.raises(rec_svc.CannotPromoteSkippedError):
        rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())


def test_promote_edits_override_defaults(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rule_id = world["rule"]
    rule = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert rule is not None
    recurring_repo.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_id,
            occurrence_date=rule.next_due,
            state=OverrideState.OVERRIDDEN,
            amount_override=250_000,
        ),
    )
    txn = rec_svc.promote_recurring(
        conn,
        USER_ID,
        rule_id,
        rec_svc.PromotionEdits(amount_minor=180_000, description="edited"),
    )
    assert txn.amount == 180_000
    assert txn.description == "edited"


def test_promote_end_of_rule_deactivates(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rent = world["rent"]
    checking = world["checking"]
    one_off = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 20),  # only one occurrence possible
            category_id=rent,
            account_id=checking,
            default_amount=100,
            default_description="one-off",
        ),
    )
    rec_svc.promote_recurring(conn, USER_ID, one_off.id, rec_svc.PromotionEdits())
    after = recurring_repo.find_rule(conn, USER_ID, one_off.id, include_deleted=True)
    assert after is not None
    assert not after.active


def test_promote_zero_amount_rejected(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        rec_svc.promote_recurring(
            conn,
            USER_ID,
            world["rule"],
            rec_svc.PromotionEdits(amount_minor=0),
        )


def test_promote_transit_cross_currency_rejected(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    transit_rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            category_id=world["transit"],
            account_id=world["checking"],
            dest_account_id=world["eur"],
            default_amount=1000,
        ),
    )
    with pytest.raises(ValidationError):
        rec_svc.promote_recurring(conn, USER_ID, transit_rule.id, rec_svc.PromotionEdits())


def test_promote_adjustment_direction_unsupported(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    adj_rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            category_id=world["reconciliation"],
            account_id=world["checking"],
            default_amount=100,
        ),
    )
    with pytest.raises(UnsupportedDirectionError):
        rec_svc.promote_recurring(conn, USER_ID, adj_rule.id, rec_svc.PromotionEdits())


def test_promote_unknown_rule(conn: sqlite3.Connection) -> None:
    with pytest.raises(rec_svc.RecurringNotFoundError):
        rec_svc.promote_recurring(conn, USER_ID, 9999, rec_svc.PromotionEdits())


def test_promote_inactive_rule(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    recurring_repo.deactivate_rule(conn, USER_ID, world["rule"])
    with pytest.raises(rec_svc.InactiveRecurringError):
        rec_svc.promote_recurring(conn, USER_ID, world["rule"], rec_svc.PromotionEdits())


def test_promote_writes_audit(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    rule_id = world["rule"]
    entries_before = len(audit_repo.list_entries(conn, "recurring_rule", rule_id))
    rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    entries_after = audit_repo.list_entries(conn, "recurring_rule", rule_id)
    # Promotion adds one audit entry on the rule mutation (update).
    assert len(entries_after) == entries_before + 1
    assert entries_after[-1].operation == "update"


def test_skip_and_advance_advances_without_promotion(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule_id = world["rule"]
    before = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert before is not None
    due = before.next_due
    new_due = rec_svc.skip_and_advance(conn, USER_ID, rule_id)
    assert new_due is not None
    assert new_due > due

    after = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert after is not None
    assert after.next_due == new_due
    # Skip is not a promotion: last_promoted_date must stay as it was.
    assert after.last_promoted_date == before.last_promoted_date
    # The ephemeral skip override has been removed after advancing.
    assert all(
        o.occurrence_date != due for o in recurring_repo.list_overrides(conn, USER_ID, rule_id)
    )


def test_skip_and_advance_end_of_rule_deactivates(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rent = world["rent"]
    checking = world["checking"]
    one_off = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 20),
            category_id=rent,
            account_id=checking,
            default_amount=100,
        ),
    )
    out = rec_svc.skip_and_advance(conn, USER_ID, one_off.id)
    assert out is None
    after = recurring_repo.find_rule(conn, USER_ID, one_off.id, include_deleted=True)
    assert after is not None
    assert not after.active


def test_skip_and_advance_unknown_rule(conn: sqlite3.Connection) -> None:
    with pytest.raises(rec_svc.RecurringNotFoundError):
        rec_svc.skip_and_advance(conn, USER_ID, 9999)


def test_skip_and_advance_inactive_rule(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    recurring_repo.deactivate_rule(conn, USER_ID, world["rule"])
    with pytest.raises(rec_svc.InactiveRecurringError):
        rec_svc.skip_and_advance(conn, USER_ID, world["rule"])


def test_promote_date_override_shifts_operation_date(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule_id = world["rule"]
    rule = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert rule is not None
    shifted = rule.next_due + _dt_module.timedelta(days=3)
    recurring_repo.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_id,
            occurrence_date=rule.next_due,
            state=OverrideState.OVERRIDDEN,
            date_override=shifted,
        ),
    )
    txn = rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    assert txn.operation_date == shifted
    # Provenance keeps the canonical occurrence date for dedup.
    assert txn.promoted_from_recurring_date == rule.next_due


def test_promote_rollback_on_set_next_due_failure(
    conn: sqlite3.Connection, world: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    rule_id = world["rule"]
    empty = TransactionFilter()
    txns_before = len(transactions_repo.list_filtered(conn, USER_ID, empty))
    before = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert before is not None

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("budget_planner.repositories.recurring.set_next_due", _boom)
    with pytest.raises(RuntimeError):
        rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())

    txns_after = len(transactions_repo.list_filtered(conn, USER_ID, empty))
    assert txns_after == txns_before
    after = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert after is not None
    assert after.next_due == before.next_due
