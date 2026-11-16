from __future__ import annotations

import datetime as dt
import sqlite3
from datetime import date

import pytest

from budget_planner.domain.enums import Cadence, OverrideState
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
)
from budget_planner.repositories import audit, recurring

USER_ID = 1


def _new_rule(account_id: int, category_id: int) -> NewRecurringRule:
    return NewRecurringRule(
        cadence=Cadence.MONTHLY,
        start_date=date(2026, 1, 1),
        category_id=category_id,
        account_id=account_id,
        default_amount=100,
        day_of_month=1,
    )


def test_create_rule_round_trip(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    assert recurring.find_rule(conn, USER_ID, rule.id) == rule
    rules = recurring.list_rules(conn, USER_ID)
    assert any(r.id == rule.id for r in rules)
    assert audit.list_entries(conn, "recurring_rule", rule.id)[0].operation.value == ("create")


def test_update_rule_fields(conn: sqlite3.Connection, account_id: int, category_id: int) -> None:
    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    updated = recurring.update_rule(
        conn,
        USER_ID,
        rule.id,
        PatchRecurringRule(
            cadence=Cadence.QUARTERLY,
            start_date=date(2026, 2, 1),
            end_date=date(2027, 1, 1),
            default_amount=250,
            active=False,
        ),
    )
    assert updated.cadence is Cadence.QUARTERLY
    assert updated.start_date == date(2026, 2, 1)
    assert updated.end_date == date(2027, 1, 1)
    assert updated.active is False


def test_deactivate_and_soft_delete(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    deactivated = recurring.deactivate_rule(conn, USER_ID, rule.id)
    assert deactivated.active is False
    recurring.soft_delete_rule(conn, USER_ID, rule.id)
    assert recurring.find_rule(conn, USER_ID, rule.id) is None
    assert recurring.find_rule(conn, USER_ID, rule.id, include_deleted=True) is not None
    recurring.soft_delete_rule(conn, USER_ID, 999)  # no-op path


def test_list_rules_active_only(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    r1 = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    r2 = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    recurring.deactivate_rule(conn, USER_ID, r2.id)
    actives = recurring.list_rules(conn, USER_ID, active_only=True)
    ids = {r.id for r in actives}
    assert r1.id in ids
    assert r2.id not in ids


def test_update_rule_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(LookupError):
        recurring.update_rule(conn, USER_ID, 999, PatchRecurringRule(active=False))


def test_create_rule_populates_next_due_from_generator(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """T-117 / ADR-0038: `next_due` is computed on create.

    For a monthly rule starting on day 1 with a start_date far in the
    past, the first canonical occurrence on-or-after today is at most
    one calendar month away.
    """

    today = dt.datetime.now(tz=dt.UTC).date()
    past_start = today - dt.timedelta(days=120)
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=past_start,
            category_id=category_id,
            account_id=account_id,
            default_amount=10_000,
            day_of_month=past_start.day,
        ),
    )
    assert rule.next_due >= today
    assert (rule.next_due - today).days <= 32
    assert rule.last_promoted_date is None


def test_create_rule_future_start_sets_next_due_to_start(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """Future-start rule: `next_due` is the start_date itself."""

    today = dt.datetime.now(tz=dt.UTC).date()
    future_start = today + dt.timedelta(days=60)
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=future_start,
            category_id=category_id,
            account_id=account_id,
            default_amount=10_000,
            day_of_month=future_start.day,
        ),
    )
    assert rule.next_due == future_start


def test_create_rule_terminal_end_date_falls_back_to_start_sentinel(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """If `end_date` has already passed, repository returns start_date as sentinel.

    The repository alone does not deactivate the rule — that is the
    migration backfill's job for pre-existing rows and the T-118 promote
    service's job going forward. Here we assert the sentinel contract.
    """

    today = dt.datetime.now(tz=dt.UTC).date()
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=today - dt.timedelta(days=400),
            end_date=today - dt.timedelta(days=10),
            category_id=category_id,
            account_id=account_id,
            default_amount=10_000,
            day_of_month=1,
        ),
    )
    assert rule.next_due == today - dt.timedelta(days=400)


def test_list_rules_surfaces_next_due_and_last_promoted(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    created = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    rules = recurring.list_rules(conn, USER_ID)
    hit = next(r for r in rules if r.id == created.id)
    assert hit.next_due == created.next_due
    assert hit.last_promoted_date is None


def test_set_next_due_round_trip(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:

    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    new_date = dt.date(2027, 6, 15)
    promoted_on = dt.date(2027, 5, 15)
    recurring.set_next_due(
        conn, USER_ID, rule.id, next_due=new_date, last_promoted_date=promoted_on
    )
    refreshed = recurring.find_rule(conn, USER_ID, rule.id)
    assert refreshed is not None
    assert refreshed.next_due == new_date
    assert refreshed.last_promoted_date == promoted_on


def test_set_next_due_accepts_null_last_promoted(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:

    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    new_date = dt.date(2027, 6, 15)
    recurring.set_next_due(conn, USER_ID, rule.id, next_due=new_date, last_promoted_date=None)
    refreshed = recurring.find_rule(conn, USER_ID, rule.id)
    assert refreshed is not None
    assert refreshed.next_due == new_date
    assert refreshed.last_promoted_date is None


def test_set_inactive_marks_rule_inactive(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    assert rule.active is True
    recurring.set_inactive(conn, USER_ID, rule.id)
    refreshed = recurring.find_rule(conn, USER_ID, rule.id)
    assert refreshed is not None
    assert refreshed.active is False


def test_patch_recurring_rule_next_due_sentinel_is_passthrough(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    """Admin-only `next_due` override via the explicit patch field."""

    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    new_date = dt.date(2028, 1, 1)
    updated = recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=new_date))
    assert updated.next_due == new_date
    # Omitting next_due keeps it untouched.
    bumped = recurring.update_rule(
        conn, USER_ID, rule.id, PatchRecurringRule(default_amount=99_999)
    )
    assert bumped.next_due == new_date


def test_override_upsert_and_delete(
    conn: sqlite3.Connection, account_id: int, category_id: int
) -> None:
    rule = recurring.create_rule(conn, USER_ID, _new_rule(account_id, category_id))
    override = recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=date(2026, 2, 1),
            state=OverrideState.OVERRIDDEN,
            amount_override=200,
            description_override="february uplift",
        ),
    )
    assert override.state is OverrideState.OVERRIDDEN

    # upsert with same key updates existing row.
    bumped = recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=date(2026, 2, 1),
            state=OverrideState.OVERRIDDEN,
            amount_override=300,
            date_override=date(2026, 2, 5),
        ),
    )
    assert bumped.id == override.id
    assert bumped.amount_override == 300
    assert bumped.date_override == date(2026, 2, 5)

    all_overrides = recurring.list_overrides(conn, USER_ID, rule.id)
    assert len(all_overrides) == 1

    recurring.delete_override(conn, USER_ID, rule.id, date(2026, 2, 1))
    assert recurring.list_overrides(conn, USER_ID, rule.id) == []
    # Deleting again is a no-op.
    recurring.delete_override(conn, USER_ID, rule.id, date(2026, 2, 1))
