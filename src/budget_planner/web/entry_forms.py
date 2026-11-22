"""Form validation for the transaction and planned entry forms (T-Q265).

Turns raw form text into typed values plus a field-keyed error map. Rules live
in services (``transit_shape_error``, ``validate_distinct_accounts``); this
module only sequences them per form and names the result for the router.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.limits import DESCRIPTION_MAX_LENGTH, length_error
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    transactions as transactions_service,
)
from budget_planner.services.account_pair import validate_distinct_accounts
from budget_planner.web.params import parse_date, parse_int, positive_amount


@dataclass(frozen=True, slots=True)
class EntryCheck:
    """Outcome of validating one entry form submission."""

    errors: dict[str, str] = field(default_factory=dict)
    op_date: date | None = None
    minor: int | None = None
    dest_id: int | None = None
    account: Account | None = None
    category: Category | None = None


def _amount(raw: str, acc: Account | None) -> tuple[int | None, dict[str, str]]:
    """Positive amount in the account's currency, with its field error (if any)."""
    if acc is None:
        return None, {}
    minor, err = positive_amount(raw, acc.currency)
    return minor, ({"amount": err} if err else {})


def _shape_error(
    conn: sqlite3.Connection, user_id: int, cat: Category, account_id: int, dest: int | None
) -> str | None:
    return transactions_service.transit_shape_error(
        conn, user_id, direction=cat.direction, account_id=account_id, dest_account_id=dest
    )


def _date_error(raw: str) -> tuple[date | None, dict[str, str]]:
    parsed = parse_date(raw)
    return parsed, ({} if parsed is not None else {"operation_date": "invalid date"})


def _description_error(description: str) -> dict[str, str]:
    too_long = length_error(description, maximum=DESCRIPTION_MAX_LENGTH)
    return {} if too_long is None else {"description": too_long}


def _unknown_errors(acc: Account | None, cat: Category | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    return errors


def _txn_create_dest(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cat: Category,
    acc: Account | None,
    account_id: int,
    dest_account_id: str,
) -> tuple[int | None, dict[str, str]]:
    """Destination of a new transaction; only transit categories read one."""
    if cat.direction != Direction.TRANSIT:
        return None, {}
    parsed = parse_int(dest_account_id) if dest_account_id else None
    if dest_account_id and parsed is None:
        return None, {"dest_account_id": "invalid destination"}
    if acc is None:
        return None, {}
    shape = _shape_error(conn, user_id, cat, account_id, parsed)
    return (parsed, {}) if shape is None else (None, {"dest_account_id": shape})


def check_txn_create(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    description: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate a new transaction (a destination is read only for transit categories)."""
    op_date, errors = _date_error(operation_date)
    errors.update(_description_error(description))
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    errors.update(_unknown_errors(acc, cat))
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    dest_id: int | None = None
    if cat is not None:
        dest_id, dest_errors = _txn_create_dest(
            conn, user_id, cat=cat, acc=acc, account_id=account_id, dest_account_id=dest_account_id
        )
        errors.update(dest_errors)
    return EntryCheck(errors, op_date, minor, dest_id, acc, cat)


def _txn_update_dest_error(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cat: Category | None,
    acc: Account | None,
    account_id: int,
    submitted_raw: str,
    submitted: int | None,
    effective: int | None,
) -> dict[str, str]:
    if submitted_raw and submitted is None:
        return {"dest_account_id": "invalid destination"}
    if acc is not None and cat is not None:
        shape = _shape_error(conn, user_id, cat, account_id, effective)
        if shape is not None:
            return {"dest_account_id": shape}
    return {}


def check_txn_update(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    existing_dest_id: int | None,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    description: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate an edited transaction; the submitted destination wins over the stored one."""
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    op_date, errors = _date_error(operation_date)
    errors.update(_description_error(description))
    errors.update(_unknown_errors(acc, cat))
    submitted = parse_int(dest_account_id) if dest_account_id else None
    effective = submitted if submitted is not None else existing_dest_id
    errors.update(
        _txn_update_dest_error(
            conn,
            user_id,
            cat=cat,
            acc=acc,
            account_id=account_id,
            submitted_raw=dest_account_id,
            submitted=submitted,
            effective=effective,
        )
    )
    same = validate_distinct_accounts(account_id, effective)
    if same is not None:
        errors["dest_account_id"] = same
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    return EntryCheck(errors, op_date, minor, submitted, acc, cat)


def _planned_dest(
    conn: sqlite3.Connection, user_id: int, account_id: int, dest_account_id: str
) -> tuple[int | None, dict[str, str]]:
    """Destination of a new planned transaction: parsed, existing and distinct from the source."""
    if not dest_account_id.strip():
        return None, {}
    try:
        dest_id = int(dest_account_id)
    except ValueError:
        return None, {"dest_account_id": "invalid dest account"}
    if accounts_service.find_by_id(conn, user_id, dest_id) is None:
        return dest_id, {"dest_account_id": "unknown dest account"}
    same = validate_distinct_accounts(account_id, dest_id)
    return dest_id, ({} if same is None else {"dest_account_id": same})


def check_planned_create(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate a new planned transaction."""
    op_date, errors = _date_error(operation_date)
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    errors.update(_unknown_errors(acc, cat))
    dest_id, dest_errors = _planned_dest(conn, user_id, account_id, dest_account_id)
    errors.update(dest_errors)
    if cat is not None and acc is not None and "dest_account_id" not in errors:
        shape = _shape_error(conn, user_id, cat, account_id, dest_id)
        if shape is not None:
            errors["dest_account_id"] = shape
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    return EntryCheck(errors, op_date, minor, dest_id, acc, cat)


def check_planned_update(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    existing_dest_id: int | None,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate an edited planned transaction; the submitted destination wins."""
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    op_date, errors = _date_error(operation_date)
    if acc is None:
        errors["account_id"] = "unknown account"
    submitted = int(dest_account_id) if dest_account_id.strip().isdigit() else None
    effective = submitted if submitted is not None else existing_dest_id
    same = validate_distinct_accounts(account_id, effective)
    if same is not None:
        errors["dest_account_id"] = same
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        errors["category_id"] = "unknown category"
    elif acc is not None and same is None:
        shape = _shape_error(conn, user_id, cat, account_id, effective)
        if shape is not None:
            errors["dest_account_id"] = shape
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    return EntryCheck(errors, op_date, minor, submitted, acc, cat)
