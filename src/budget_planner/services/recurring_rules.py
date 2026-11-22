"""Recurring rule and override entry points with their validation (T-Q241, T-Q285, ADR-0142).

A write validates the rule (stop date not before start, anchor day 1 to 31, amount not negative,
description length, transit shape) before its one repository mutation; failures raise
``ValidationError`` and write nothing. Re-exported by ``services.recurring``.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

from budget_planner.domain.limits import DESCRIPTION_MAX_LENGTH, length_error
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
    RecurringOverride,
    RecurringRule,
    day_of_month_error,
    end_date_error,
)
from budget_planner.repositories import categories as categories_repo, recurring as recurring_repo
from budget_planner.services._promotion import ValidationError
from budget_planner.services.transactions import check_transit_shape


def _validate_rule(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    start_date: dt.date,
    end_date: dt.date | None,
    category_id: int,
    account_id: int,
    dest_account_id: int | None,
    default_amount: int,
    description: str,
    day_of_month: int | None,
) -> None:
    """Domain rules of a recurring rule; raises :class:`ValidationError` with the exact message."""
    if (bad := end_date_error(start_date, end_date)) is not None:
        raise ValidationError(f"end date {bad}")
    if (bad := day_of_month_error(day_of_month)) is not None:
        raise ValidationError(bad)
    if default_amount < 0:
        raise ValidationError("amount must not be negative")
    if (bad := length_error(description, maximum=DESCRIPTION_MAX_LENGTH)) is not None:
        raise ValidationError(f"description {bad}")
    category = categories_repo.find_by_id(conn, user_id, category_id, include_deleted=True)
    if category is not None:
        check_transit_shape(
            conn,
            user_id,
            direction=category.direction,
            account_id=account_id,
            dest_account_id=dest_account_id,
        )


def _patched_end(rule: RecurringRule, patch: PatchRecurringRule) -> dt.date | None:
    """Stop date after ``patch``: a date sets it, ``None`` clears it, the sentinel keeps it."""
    if patch.end_date is None or isinstance(patch.end_date, dt.date):
        return patch.end_date
    return rule.end_date


def find_rule(
    conn: sqlite3.Connection, user_id: int, rule_id: int, *, include_deleted: bool = False
) -> RecurringRule | None:
    """The caller's rule, or ``None`` (soft-deleted rows only with ``include_deleted``)."""
    return recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=include_deleted)


def list_rules(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    active_only: bool = False,
    include_deleted: bool = False,
) -> list[RecurringRule]:
    """The caller's rules."""
    return recurring_repo.list_rules(
        conn, user_id, active_only=active_only, include_deleted=include_deleted
    )


def list_overrides(
    conn: sqlite3.Connection, user_id: int, rule_id: int, *, include_consumed: bool = False
) -> list[RecurringOverride]:
    """Overrides of one rule (unconsumed unless ``include_consumed``)."""
    return recurring_repo.list_overrides(conn, user_id, rule_id, include_consumed=include_consumed)


def create_rule(conn: sqlite3.Connection, user_id: int, data: NewRecurringRule) -> RecurringRule:
    """Create a rule after :func:`_validate_rule` (one repository mutation)."""
    _validate_rule(
        conn,
        user_id,
        start_date=data.start_date,
        end_date=data.end_date,
        category_id=data.category_id,
        account_id=data.account_id,
        dest_account_id=data.dest_account_id,
        default_amount=data.default_amount,
        description=data.default_description,
        day_of_month=data.day_of_month,
    )
    return recurring_repo.create_rule(conn, user_id, data)


def update_rule(
    conn: sqlite3.Connection, user_id: int, rule_id: int, data: PatchRecurringRule
) -> RecurringRule:
    """Patch a rule; the merged result must satisfy the creation rules."""
    rule = recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=True)
    if rule is not None:
        start = rule.start_date if data.start_date is None else data.start_date
        end = _patched_end(rule, data)
        _validate_rule(
            conn,
            user_id,
            start_date=start,
            end_date=end,
            category_id=rule.category_id if data.category_id is None else data.category_id,
            account_id=rule.account_id if data.account_id is None else data.account_id,
            dest_account_id=(
                rule.dest_account_id if data.dest_account_id is None else data.dest_account_id
            ),
            default_amount=(
                rule.default_amount if data.default_amount is None else data.default_amount
            ),
            description=(
                rule.default_description
                if data.default_description is None
                else data.default_description
            ),
            day_of_month=rule.day_of_month if data.day_of_month is None else data.day_of_month,
        )
    return recurring_repo.update_rule(conn, user_id, rule_id, data)


def deactivate_rule(conn: sqlite3.Connection, user_id: int, rule_id: int) -> RecurringRule:
    """Mark a rule inactive (one repository mutation)."""
    return recurring_repo.deactivate_rule(conn, user_id, rule_id)


def upsert_override(
    conn: sqlite3.Connection, user_id: int, data: NewRecurringOverride
) -> RecurringOverride:
    """Create or replace the sparse override of one occurrence."""
    return recurring_repo.upsert_override(conn, user_id, data)


def delete_override(
    conn: sqlite3.Connection, user_id: int, rule_id: int, occurrence_date: dt.date
) -> None:
    """Remove the override of one occurrence."""
    recurring_repo.delete_override(conn, user_id, rule_id, occurrence_date)
