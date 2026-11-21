"""Mutation-kill tests for ``services/recurring`` (T-Q225, ADR-0131).

Complements ``test_recurring.py`` (T-022 / T-118 / T-Q211): every case asserts
exact values (full ``Occurrence`` equality, audit row columns, exception
arguments, boundary days) so the survivors from the Mutmut 3.7.0 baseline
cannot pass unnoticed. Each test names the mutants it kills in its docstring.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, date, datetime

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
    Occurrence,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import recurring as rec_svc
from budget_planner.services._promotion import ValidationError

USER_ID = 1
OTHER_USER_ID = 2
_FORMULA_MSG = (
    "formula resolved to a non-positive amount — edit the formula or override this occurrence"
)


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def _rule(
    *,
    cadence: Cadence = Cadence.MONTHLY,
    start_date: date = date(2026, 1, 15),
    end_date: date | None = None,
    day_of_month: int | None = None,
    month_of_year: int | None = None,
    active: bool = True,
    next_due: date | None = None,
) -> RecurringRule:
    return RecurringRule(
        id=7,
        user_id=1,
        cadence=cadence,
        start_date=start_date,
        end_date=end_date,
        category_id=11,
        account_id=3,
        dest_account_id=4,
        default_amount=12_345,
        default_description="gym",
        day_of_month=day_of_month,
        month_of_year=month_of_year,
        active=active,
        next_due=next_due or start_date,
        last_promoted_date=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        deleted_at=None,
    )


def _override(
    override_id: int,
    occurrence_date: date,
    *,
    state: OverrideState = OverrideState.OVERRIDDEN,
    amount: int | None = None,
) -> RecurringOverride:
    return RecurringOverride(
        id=override_id,
        rule_id=7,
        occurrence_date=occurrence_date,
        state=state,
        amount_override=amount,
        description_override=None,
        date_override=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_generated_occurrence_carries_every_rule_field() -> None:
    """Kills _mk_occurrence rule_id/category_id/dest/description/is_* mutants."""
    occs = rec_svc.generate_occurrences(_rule(), date(2026, 1, 15), date(2026, 1, 15))
    assert occs == (
        Occurrence(
            rule_id=7,
            occurrence_date=date(2026, 1, 15),
            effective_date=date(2026, 1, 15),
            category_id=11,
            account_id=3,
            dest_account_id=4,
            amount=12_345,
            description="gym",
            is_overridden=False,
            is_skipped=False,
        ),
    )


def test_overridden_occurrence_keeps_identity_fields() -> None:
    """Kills _apply_single_override rule_id/category_id/dest/is_skipped mutants."""
    occs = rec_svc.generate_occurrences(_rule(), date(2026, 1, 15), date(2026, 1, 15))
    out = rec_svc.apply_overrides(occs, [_override(1, date(2026, 1, 15), amount=999)])
    assert out == (
        Occurrence(
            rule_id=7,
            occurrence_date=date(2026, 1, 15),
            effective_date=date(2026, 1, 15),
            category_id=11,
            account_id=3,
            dest_account_id=4,
            amount=999,
            description="gym",
            is_overridden=True,
            is_skipped=False,
        ),
    )


def test_single_day_range_on_occurrence_is_inclusive() -> None:
    """Kills generate_occurrences `hard_end <= hard_start`."""
    occs = rec_svc.generate_occurrences(_rule(), date(2026, 3, 15), date(2026, 3, 15))
    assert [o.occurrence_date for o in occs] == [date(2026, 3, 15)]


def test_month_of_year_is_ignored_for_non_yearly_cadence() -> None:
    """Kills `cadence is YEARLY and month_of_year` -> `or`."""
    rule = _rule(cadence=Cadence.MONTHLY, start_date=date(2026, 1, 15), month_of_year=6)
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2026, 3, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 1, 15),
        date(2026, 2, 15),
        date(2026, 3, 15),
    ]


def test_yearly_month_of_year_equal_to_start_keeps_first_year() -> None:
    """Kills `candidate < start_date` -> `<=` (candidate == start must not roll)."""
    rule = _rule(cadence=Cadence.YEARLY, start_date=date(2026, 8, 15), month_of_year=8)
    occs = rec_svc.generate_occurrences(rule, date(2026, 1, 1), date(2028, 12, 31))
    assert [o.occurrence_date for o in occs] == [
        date(2026, 8, 15),
        date(2027, 8, 15),
        date(2028, 8, 15),
    ]


def test_generator_raises_when_range_exceeds_iteration_guard() -> None:
    """Kills the guard-message mutants (None / XX-wrapped / upper-cased)."""
    with pytest.raises(RuntimeError) as exc:
        rec_svc.generate_occurrences(_rule(), date(2026, 1, 1), date(9999, 12, 31))
    assert exc.value.args == ("occurrence generator did not terminate",)


# --- apply_overrides logging / ordering -------------------------------------
def test_no_warning_without_duplicate_overrides(caplog: pytest.LogCaptureFixture) -> None:
    """Kills `occurrence_date in seen` -> `not in seen`."""
    occs = rec_svc.generate_occurrences(_rule(), date(2026, 1, 1), date(2026, 3, 31))
    overrides = [
        _override(1, date(2026, 1, 15), amount=1),
        _override(2, date(2026, 2, 15), amount=2),
    ]
    with caplog.at_level(logging.DEBUG, logger="budget_planner.services.recurring"):
        out = rec_svc.apply_overrides(occs, overrides)
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []
    assert [o.amount for o in out] == [1, 2, 12_345]


def test_duplicate_override_warning_message_is_exact(caplog: pytest.LogCaptureFixture) -> None:
    """Kills warning format / rule_id / occurrence_date argument mutants."""
    occs = rec_svc.generate_occurrences(_rule(), date(2026, 1, 15), date(2026, 1, 15))
    overrides = [
        _override(1, date(2026, 1, 15), amount=1),
        _override(2, date(2026, 1, 15), amount=2),
    ]
    with caplog.at_level(logging.DEBUG, logger="budget_planner.services.recurring"):
        out = rec_svc.apply_overrides(occs, overrides)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == ["overrides collide on (rule_id=7, occurrence_date=2026-01-15); last-wins"]
    assert [o.amount for o in out] == [2]


def test_orphan_override_debug_message_and_later_override_still_applies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Kills orphan debug message/args mutants and `continue` -> `break`."""
    occs = rec_svc.generate_occurrences(_rule(), date(2026, 1, 15), date(2026, 1, 15))
    overrides = [
        _override(1, date(2026, 1, 20), amount=5),  # orphan, sorts first
        _override(2, date(2026, 1, 15), amount=6),
    ]
    with caplog.at_level(logging.DEBUG, logger="budget_planner.services.recurring"):
        out = rec_svc.apply_overrides(occs, overrides)
    debug = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert debug == ["orphan override dropped: rule_id=7 date=2026-01-20"]
    assert [o.amount for o in out] == [6]


# --- advance_next_due / occurrence_in_month ---------------------------------
def test_advance_next_due_inactive_rule_still_advances() -> None:
    """Kills `replace(rule, active=True)` -> `replace(rule)`."""
    rule = _rule(active=False, start_date=date(2026, 1, 15))
    assert rec_svc.advance_next_due(rule, date(2026, 1, 15)) == date(2026, 2, 15)


def test_advance_next_due_day_after_from_date_is_included() -> None:
    """Kills the `from_date + 1 day` -> `+ 2 days` mutant."""
    rule = _rule(start_date=date(2026, 1, 15))
    assert rec_svc.advance_next_due(rule, date(2026, 3, 14)) == date(2026, 3, 15)


def test_occurrence_in_month_first_day_occurrence_found() -> None:
    """Kills `range_start = day 2`."""
    rule = _rule(start_date=date(2026, 1, 1))
    assert rec_svc.occurrence_in_month(rule, 2026, 3) == date(2026, 3, 1)


def test_occurrence_in_month_does_not_leak_into_next_month() -> None:
    """Kills range_end `+1 day`, `month + 2`, `day 2` mutants (quarterly: Mar has none)."""
    rule = _rule(cadence=Cadence.QUARTERLY, start_date=date(2026, 1, 1))
    assert rec_svc.occurrence_in_month(rule, 2026, 3) is None
    assert rec_svc.occurrence_in_month(rule, 2026, 4) == date(2026, 4, 1)


def test_occurrence_in_month_last_day_occurrence_found() -> None:
    """Kills range_end `- 2 days`."""
    rule = _rule(start_date=date(2026, 1, 31))
    assert rec_svc.occurrence_in_month(rule, 2026, 3) == date(2026, 3, 31)


# ---------------------------------------------------------------------------
# DB-backed fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts_repo.create(conn, USER_ID, NewAccount(name="Checking", currency="PLN")).id
    savings = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN")).id
    rent = categories_repo.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    transit = categories_repo.find_by_name(conn, USER_ID, "Transit")
    assert transit is not None
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
    # create_rule seeds next_due from the real clock; pin it so dates are deterministic.
    recurring_repo.set_next_due(
        conn, USER_ID, rule.id, next_due=date(2026, 1, 5), last_promoted_date=None
    )
    return {
        "checking": checking,
        "savings": savings,
        "rent": rent,
        "transit": transit.id,
        "rule": rule.id,
    }


def _new_rule(
    conn: sqlite3.Connection, world: dict[str, int], **overrides: object
) -> RecurringRule:
    fields: dict[str, object] = {
        "cadence": Cadence.MONTHLY,
        "start_date": date(2026, 1, 5),
        "category_id": world["rent"],
        "account_id": world["checking"],
        "default_amount": 1_000,
        **overrides,
    }
    rule = recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(**fields),  # type: ignore[arg-type]  # fields are NewRecurringRule kwargs
    )
    start = fields["start_date"]
    assert isinstance(start, date)
    recurring_repo.set_next_due(conn, USER_ID, rule.id, next_due=start, last_promoted_date=None)
    found = recurring_repo.find_rule(conn, USER_ID, rule.id)
    assert found is not None
    return found


def _audit_rows(conn: sqlite3.Connection, entity_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM audit_log WHERE entity_type = 'recurring_rule' "
            "AND entity_id = ? ORDER BY id",
            (entity_id,),
        )
    )


def _seed_second_user(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
        (OTHER_USER_ID, "other", "other@example.test", "x"),
    )


# ---------------------------------------------------------------------------
# error arguments
# ---------------------------------------------------------------------------
def test_promote_errors_carry_the_rule_id(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    """Kills the `Error(rule_id)` -> `Error(None)` mutants in promote/skip."""
    with pytest.raises(rec_svc.RecurringNotFoundError) as nf:
        rec_svc.promote_recurring(conn, USER_ID, 9999, rec_svc.PromotionEdits())
    assert nf.value.args == (9999,)
    with pytest.raises(rec_svc.RecurringNotFoundError) as nf2:
        rec_svc.skip_and_advance(conn, USER_ID, 9998)
    assert nf2.value.args == (9998,)

    rule_id = world["rule"]
    rule = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert rule is not None
    recurring_repo.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_id, occurrence_date=rule.next_due, state=OverrideState.SKIPPED
        ),
    )
    with pytest.raises(rec_svc.CannotPromoteSkippedError) as sk:
        rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    assert sk.value.args == (rule_id,)

    recurring_repo.deactivate_rule(conn, USER_ID, rule_id)
    with pytest.raises(rec_svc.InactiveRecurringError) as ia:
        rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    assert ia.value.args == (rule_id,)
    with pytest.raises(rec_svc.InactiveRecurringError) as ia2:
        rec_svc.skip_and_advance(conn, USER_ID, rule_id)
    assert ia2.value.args == (rule_id,)


def test_other_users_rule_is_not_found(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    """A second user cannot promote or skip user 1's rule, and no audit row is written."""
    _seed_second_user(conn)
    before = _audit_rows(conn, world["rule"])
    with pytest.raises(rec_svc.RecurringNotFoundError):
        rec_svc.promote_recurring(conn, OTHER_USER_ID, world["rule"], rec_svc.PromotionEdits())
    with pytest.raises(rec_svc.RecurringNotFoundError):
        rec_svc.skip_and_advance(conn, OTHER_USER_ID, world["rule"])
    assert len(_audit_rows(conn, world["rule"])) == len(before)


# ---------------------------------------------------------------------------
# formula guard (ADR-0047)
# ---------------------------------------------------------------------------
def _formula_rule(
    conn: sqlite3.Connection, world: dict[str, int], terms: tuple[FormulaTerm, ...]
) -> RecurringRule:
    cat = categories_repo.create(
        conn, USER_ID, NewCategory(name="Derived", direction=Direction.EXPENSE)
    ).id
    return _new_rule(
        conn,
        world,
        category_id=cat,
        default_amount=1,
        amount_formula=AmountFormula(terms=terms),
    )


def _source_terms(
    world: dict[str, int], *, bps: int, minus_bps: int = 0
) -> tuple[FormulaTerm, ...]:
    src = (world["rent"],)
    terms = [FormulaTerm(sign="+", coefficient_bps=bps, source_category_ids=src)]
    if minus_bps:
        terms.append(FormulaTerm(sign="-", coefficient_bps=minus_bps, source_category_ids=src))
    return tuple(terms)


def test_formula_resolving_to_zero_raises_formula_message(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills formula-guard condition (`is None`, `<`) and message mutants."""
    rule = _formula_rule(conn, world, _source_terms(world, bps=10_000, minus_bps=10_000))
    with pytest.raises(ValidationError) as exc:
        rec_svc.promote_recurring(conn, USER_ID, rule.id, rec_svc.PromotionEdits())
    assert exc.value.args == (_FORMULA_MSG,)


def test_formula_resolving_to_negative_raises_formula_message(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule = _formula_rule(conn, world, _source_terms(world, bps=5_000, minus_bps=10_000))
    with pytest.raises(ValidationError) as exc:
        rec_svc.promote_recurring(conn, USER_ID, rule.id, rec_svc.PromotionEdits())
    assert exc.value.args == (_FORMULA_MSG,)


def test_formula_resolving_to_one_minor_unit_is_accepted(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills `amount <= 0` -> `amount <= 1` (1 bp of a 10_000 source is exactly 1)."""
    source = categories_repo.create(
        conn, USER_ID, NewCategory(name="Tiny", direction=Direction.EXPENSE)
    )
    _new_rule(conn, world, category_id=source.id, default_amount=10_000)
    rule = _formula_rule(
        conn,
        world,
        (FormulaTerm(sign="+", coefficient_bps=1, source_category_ids=(source.id,)),),
    )
    txn = rec_svc.promote_recurring(conn, USER_ID, rule.id, rec_svc.PromotionEdits())
    assert txn.amount == 1


def test_explicit_amount_edit_bypasses_formula_guard(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule = _formula_rule(conn, world, _source_terms(world, bps=10_000, minus_bps=10_000))
    txn = rec_svc.promote_recurring(
        conn, USER_ID, rule.id, rec_svc.PromotionEdits(amount_minor=4_200)
    )
    assert txn.amount == 4_200


# ---------------------------------------------------------------------------
# promotion field plumbing
# ---------------------------------------------------------------------------
def test_promote_with_soft_deleted_category_still_succeeds(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills category lookup `include_deleted` True -> None/False/omitted."""
    categories_repo.soft_delete(conn, USER_ID, world["rent"])
    txn = rec_svc.promote_recurring(conn, USER_ID, world["rule"], rec_svc.PromotionEdits())
    assert txn.category_id == world["rent"]
    assert txn.amount == 200_000


def test_promote_transit_rule_persists_both_accounts(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills user_id/account_id/dest_account_id None mutants in validate + NewTransaction."""
    rule = _new_rule(conn, world, category_id=world["transit"], dest_account_id=world["savings"])
    txn = rec_svc.promote_recurring(conn, USER_ID, rule.id, rec_svc.PromotionEdits())
    assert txn.account_id == world["checking"]
    assert txn.dest_account_id == world["savings"]
    assert txn.amount == 1_000
    stored = transactions_repo.find_by_id(conn, USER_ID, txn.id)
    assert stored is not None
    assert stored.dest_account_id == world["savings"]


def test_promote_transit_rule_without_dest_is_rejected(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    rule = _new_rule(conn, world, category_id=world["transit"])
    with pytest.raises(ValidationError):
        rec_svc.promote_recurring(conn, USER_ID, rule.id, rec_svc.PromotionEdits())


# ---------------------------------------------------------------------------
# audit attribution
# ---------------------------------------------------------------------------
def _assert_rule_audit(
    row: sqlite3.Row, before: RecurringRule, after: RecurringRule, rule_id: int
) -> None:
    assert row["entity_type"] == "recurring_rule"
    assert row["entity_id"] == rule_id
    assert row["operation"] == "update"
    assert row["user_id"] == USER_ID
    assert row["actor_user_id"] == USER_ID
    prev = json.loads(row["prev_json"])
    new = json.loads(row["new_json"])
    assert prev["next_due"] == before.next_due.isoformat()
    assert prev["last_promoted_date"] == (
        before.last_promoted_date.isoformat() if before.last_promoted_date else None
    )
    assert new["next_due"] == after.next_due.isoformat()
    assert new["last_promoted_date"] == (
        after.last_promoted_date.isoformat() if after.last_promoted_date else None
    )
    assert new["id"] == prev["id"] == rule_id
    assert new["user_id"] == prev["user_id"] == USER_ID


def test_promote_audit_row_attributes_user_and_diff(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills audit `user_id=None` and promote `updated_rule` mutants."""
    rule_id = world["rule"]
    before = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert before is not None
    n_before = len(_audit_rows(conn, rule_id))
    rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    after = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert after is not None
    rows = _audit_rows(conn, rule_id)
    assert len(rows) == n_before + 1
    _assert_rule_audit(rows[-1], before, after, rule_id)
    assert after.next_due == date(2026, 2, 5)
    assert after.last_promoted_date == date(2026, 1, 5)


def test_promote_audit_not_visible_to_other_user(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _seed_second_user(conn)
    rec_svc.promote_recurring(conn, USER_ID, world["rule"], rec_svc.PromotionEdits())
    rows = conn.execute("SELECT user_id FROM audit_log WHERE entity_type = 'recurring_rule'")
    assert OTHER_USER_ID not in {r["user_id"] for r in rows}


def test_skip_audit_row_attributes_user_and_entity_type(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills skip audit entity_type / user_id mutants."""
    rule_id = world["rule"]
    before = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert before is not None
    n_before = len(_audit_rows(conn, rule_id))
    new_due = rec_svc.skip_and_advance(conn, USER_ID, rule_id)
    assert new_due == date(2026, 2, 5)
    after = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert after is not None
    rows = _audit_rows(conn, rule_id)
    # The override upsert/delete emit no recurring_rule rows; the rule update emits one.
    assert len(rows) == n_before + 1
    _assert_rule_audit(rows[-1], before, after, rule_id)


def test_skip_preserves_last_promoted_date(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    """Kills `last_promoted_date=rule.last_promoted_date` -> None."""
    rule_id = world["rule"]
    rec_svc.promote_recurring(conn, USER_ID, rule_id, rec_svc.PromotionEdits())
    assert rec_svc.skip_and_advance(conn, USER_ID, rule_id) == date(2026, 3, 5)
    after = recurring_repo.find_rule(conn, USER_ID, rule_id)
    assert after is not None
    assert after.last_promoted_date == date(2026, 1, 5)
    assert after.next_due == date(2026, 3, 5)


# ---------------------------------------------------------------------------
# batch_promote_due ordering and boundary
# ---------------------------------------------------------------------------
def test_batch_promotes_rule_due_exactly_today(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills `next_due > today` -> `>=`."""
    result = rec_svc.batch_promote_due(conn, USER_ID, date(2026, 1, 5))
    assert result.advanced_rule_ids == (world["rule"],)
    assert len(result.promoted_txn_ids) == 1
    assert result.skipped_rule_ids == ()


def test_batch_not_due_rule_does_not_stop_later_due_rule(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills the not-due `continue` -> `break` (rules are ordered by start_date)."""
    recurring_repo.set_next_due(
        conn, USER_ID, world["rule"], next_due=date(2026, 9, 1), last_promoted_date=None
    )
    later = _new_rule(conn, world, start_date=date(2026, 2, 1), default_amount=777)
    result = rec_svc.batch_promote_due(conn, USER_ID, date(2026, 2, 1))
    assert result.advanced_rule_ids == (later.id,)
    assert len(result.promoted_txn_ids) == 1
    txn = transactions_repo.find_by_id(conn, USER_ID, result.promoted_txn_ids[0])
    assert txn is not None
    assert txn.amount == 777
    assert txn.promoted_from_recurring_rule_id == later.id


def test_batch_skipped_rule_does_not_stop_later_due_rule(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills the skipped-override `continue` -> `break`."""
    rule_id = world["rule"]
    recurring_repo.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule_id, occurrence_date=date(2026, 1, 5), state=OverrideState.SKIPPED
        ),
    )
    later = _new_rule(conn, world, start_date=date(2026, 1, 20), default_amount=555)
    result = rec_svc.batch_promote_due(conn, USER_ID, date(2026, 1, 31))
    assert result.skipped_rule_ids == (rule_id,)
    assert result.advanced_rule_ids == (later.id,)
    assert len(result.promoted_txn_ids) == 1


# ---------------------------------------------------------------------------
# expand_unpromoted / linked_occurrence_keys
# ---------------------------------------------------------------------------
def test_expand_unpromoted_window_end_equal_to_start_is_inclusive(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills `start > window_end` -> `>=`."""
    rule = recurring_repo.find_rule(conn, USER_ID, world["rule"])
    assert rule is not None
    occs = rec_svc.expand_unpromoted(conn, USER_ID, rule, [], date(2026, 1, 1), date(2026, 1, 5))
    assert [o.occurrence_date for o in occs] == [date(2026, 1, 5)]
    assert (
        rec_svc.expand_unpromoted(conn, USER_ID, rule, [], date(2026, 1, 1), date(2026, 1, 4)) == ()
    )


def test_linked_occurrence_keys_only_unpromoted_linked_rows(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    """Kills `PlannedFilter(promoted=None)` and the `and` -> `or` mutant."""
    rule_id = world["rule"]

    def _planned(**kwargs: object) -> int:
        data = NewPlannedTransaction(
            operation_date=date(2026, 1, 5),
            category_id=world["rent"],
            account_id=world["checking"],
            amount=100,
            **kwargs,  # type: ignore[arg-type]  # kwargs are NewPlannedTransaction fields
        )
        return planned_repo.create(conn, USER_ID, data).id

    _planned(recurring_rule_id=rule_id, occurrence_date=date(2026, 1, 5))
    promoted_id = _planned(recurring_rule_id=rule_id, occurrence_date=date(2026, 2, 5))
    _planned(occurrence_date=date(2026, 3, 5))  # no rule: must not suppress anything
    _planned(recurring_rule_id=rule_id)  # no occurrence date
    _planned()  # plain planned row
    txn = transactions_repo.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 2, 5),
            category_id=world["rent"],
            account_id=world["checking"],
            amount=100,
        ),
    )
    planned_repo.stamp_promotion(conn, USER_ID, promoted_id, txn.id)

    assert rec_svc.linked_occurrence_keys(conn, USER_ID) == frozenset({(rule_id, date(2026, 1, 5))})
    _seed_second_user(conn)
    assert rec_svc.linked_occurrence_keys(conn, OTHER_USER_ID) == frozenset()
