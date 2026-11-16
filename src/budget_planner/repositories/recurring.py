"""Recurring rules + sparse overrides repository (ADR-0013 / ADR-0038 / ADR-0045).

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every rule-level function takes ``user_id`` as the first positional arg after
``conn``; every SELECT / UPDATE / DELETE on ``recurring_rules`` carries
``user_id = :user_id``. Override queries scope through the parent
``recurring_rules.user_id`` via FK join predicate — see ADR-0061 §2. The
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from datetime import date
from typing import Any

from budget_planner.domain.enums import Cadence, OverrideState
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required, require_owned
from budget_planner.services.recurring import first_due_on_or_after

_RULE_COLUMNS = (
    "id, user_id, cadence, start_date, end_date, category_id, account_id, "
    "dest_account_id, default_amount, default_description, day_of_month, "
    "month_of_year, active, next_due, last_promoted_date, amount_formula, "
    "created_at, updated_at, deleted_at"
)


def _formula_to_json(formula: AmountFormula | None) -> str | None:
    """Serialise `AmountFormula` to v2 JSON (ADR-0047)."""
    if formula is None:
        return None
    return json.dumps(
        {
            "schema_version": formula.schema_version,
            "terms": [
                {
                    "sign": term.sign,
                    "coefficient_bps": term.coefficient_bps,
                    "source_category_ids": list(term.source_category_ids),
                }
                for term in formula.terms
            ],
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _formula_from_json(raw: str | None) -> AmountFormula | None:
    """Parse `recurring_rules.amount_formula` JSON into `AmountFormula`."""
    if raw is None:
        return None
    data = json.loads(raw)
    schema = int(data.get("schema_version", 1))
    if schema == 1:
        # Pre-ADR-0047 single-term shape.
        return AmountFormula(
            schema_version=1,
            terms=(
                FormulaTerm(
                    sign="+",
                    coefficient_bps=int(data["coefficient_bps"]),
                    source_category_ids=tuple(int(v) for v in data["source_category_ids"]),
                ),
            ),
        )
    # v2 and anything we treat as v2-compatible until a tier-B/C ADR lands.
    return AmountFormula(
        schema_version=schema,
        terms=tuple(
            FormulaTerm(
                sign=term["sign"],
                coefficient_bps=int(term["coefficient_bps"]),
                source_category_ids=tuple(int(v) for v in term["source_category_ids"]),
            )
            for term in data["terms"]
        ),
    )


_OVERRIDE_COLUMNS = (
    "id, rule_id, occurrence_date, state, amount_override, description_override, "
    "date_override, created_at, promoted_to_txn_id"
)


def _row_to_rule(row: sqlite3.Row) -> RecurringRule:
    return RecurringRule(
        id=row["id"],
        user_id=row["user_id"],
        cadence=Cadence(row["cadence"]),
        start_date=date.fromisoformat(row["start_date"]),
        end_date=(date.fromisoformat(row["end_date"]) if row["end_date"] is not None else None),
        category_id=row["category_id"],
        account_id=row["account_id"],
        dest_account_id=row["dest_account_id"],
        default_amount=row["default_amount"],
        default_description=row["default_description"],
        day_of_month=row["day_of_month"],
        month_of_year=row["month_of_year"],
        active=bool(row["active"]),
        next_due=date.fromisoformat(row["next_due"]),
        last_promoted_date=(
            date.fromisoformat(row["last_promoted_date"])
            if row["last_promoted_date"] is not None
            else None
        ),
        amount_formula=_formula_from_json(row["amount_formula"]),
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        deleted_at=parse_dt(row["deleted_at"]),
    )


def _compute_initial_next_due(data: NewRecurringRule, user_id: int, today: date) -> date:
    """Return the earliest canonical occurrence on-or-after ``max(start, today)``."""
    stub = RecurringRule(
        id=0,
        user_id=user_id,
        cadence=data.cadence,
        start_date=data.start_date,
        end_date=data.end_date,
        category_id=data.category_id,
        account_id=data.account_id,
        dest_account_id=data.dest_account_id,
        default_amount=data.default_amount,
        default_description=data.default_description,
        day_of_month=data.day_of_month,
        month_of_year=data.month_of_year,
        active=True,
        next_due=data.start_date,  # placeholder; helper doesn't read it
        last_promoted_date=None,
        amount_formula=data.amount_formula,
        created_at=dt.datetime.now(dt.UTC),
        updated_at=dt.datetime.now(dt.UTC),
        deleted_at=None,
    )
    return first_due_on_or_after(stub, today)


def _row_to_override(row: sqlite3.Row) -> RecurringOverride:
    return RecurringOverride(
        id=row["id"],
        rule_id=row["rule_id"],
        occurrence_date=date.fromisoformat(row["occurrence_date"]),
        state=OverrideState(row["state"]),
        amount_override=row["amount_override"],
        description_override=row["description_override"],
        date_override=(
            date.fromisoformat(row["date_override"]) if row["date_override"] is not None else None
        ),
        created_at=parse_dt_required(row["created_at"]),
        promoted_to_txn_id=row["promoted_to_txn_id"],
    )


def find_rule(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    include_deleted: bool = False,
) -> RecurringRule | None:
    sql = f"SELECT {_RULE_COLUMNS} FROM recurring_rules WHERE id = ? AND user_id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (rule_id, user_id)).fetchone()
    return _row_to_rule(row) if row is not None else None


def list_rules(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    active_only: bool = False,
    include_deleted: bool = False,
) -> list[RecurringRule]:
    sql = f"SELECT {_RULE_COLUMNS} FROM recurring_rules WHERE user_id = ?"
    if active_only:
        sql += " AND active = 1"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    sql += " ORDER BY start_date ASC, id ASC"
    return [_row_to_rule(r) for r in conn.execute(sql, (user_id,)).fetchall()]


def _normalise_rule_patch(changes: dict[str, Any]) -> dict[str, Any]:
    norm: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "cadence":
            norm[key] = value.value
        elif key in {"start_date", "next_due"} and value is not None:
            norm[key] = value.isoformat()
        elif key == "end_date":
            # end_date is sentinel-nullable (ADR-0063). The caller may clear
            # it by patching with None.
            norm[key] = value.isoformat() if value is not None else None
        elif key == "active":
            norm[key] = int(bool(value))
        elif key == "amount_formula":
            norm[key] = _formula_to_json(value)
        else:
            norm[key] = value
    return norm


def create_rule(conn: sqlite3.Connection, user_id: int, data: NewRecurringRule) -> RecurringRule:
    require_owned(
        conn,
        user_id,
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )
    today = dt.date.today()  # noqa: DTZ011 — date-only anchor; display tz applies at render
    initial_next_due = _compute_initial_next_due(data, user_id, today)

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringRule]:
        cursor = c.execute(
            "INSERT INTO recurring_rules("
            "user_id, cadence, start_date, end_date, category_id, account_id, "
            "dest_account_id, default_amount, default_description, "
            "day_of_month, month_of_year, active, next_due, amount_formula) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_id,
                data.cadence.value,
                data.start_date.isoformat(),
                data.end_date.isoformat() if data.end_date else None,
                data.category_id,
                data.account_id,
                data.dest_account_id,
                data.default_amount,
                data.default_description,
                data.day_of_month,
                data.month_of_year,
                int(data.active),
                initial_next_due.isoformat(),
                _formula_to_json(data.amount_formula),
            ),
        )
        new_id = int(cursor.lastrowid or 0)
        created = find_rule(c, user_id, new_id)
        assert created is not None
        return new_id, created

    return mutate(
        conn,
        entity_type="recurring_rule",
        operation="create",
        prev=None,
        action=_action,
    )


def set_next_due(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    next_due: date,
    last_promoted_date: date | None,
) -> None:
    """Thin helper for the T-118 promotion service.

    Audit-free: the orchestrating service writes the paired audit entry.
    """
    conn.execute(
        "UPDATE recurring_rules SET next_due = ?, last_promoted_date = ?, "
        "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
        "WHERE id = ? AND user_id = ?",
        (
            next_due.isoformat(),
            last_promoted_date.isoformat() if last_promoted_date is not None else None,
            rule_id,
            user_id,
        ),
    )


def set_inactive(conn: sqlite3.Connection, user_id: int, rule_id: int) -> None:
    """Thin helper for the T-118 promotion service — mark a rule inactive."""
    conn.execute(
        "UPDATE recurring_rules SET active = 0, "
        "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
        "WHERE id = ? AND user_id = ?",
        (rule_id, user_id),
    )


def update_rule(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    data: PatchRecurringRule,
) -> RecurringRule:
    prev = find_rule(conn, user_id, rule_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"recurring_rule {rule_id} not found")
    require_owned(
        conn,
        user_id,
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )
    changes = _normalise_rule_patch(data.as_dict())

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringRule]:
        if changes:
            sets = [f"{field} = ?" for field in changes]
            sets.append("updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")
            c.execute(
                f"UPDATE recurring_rules SET {', '.join(sets)} WHERE id = ? AND user_id = ?",
                (*changes.values(), rule_id, user_id),
            )
        updated = find_rule(c, user_id, rule_id, include_deleted=True)
        assert updated is not None
        return rule_id, updated

    return mutate(
        conn,
        entity_type="recurring_rule",
        operation="update",
        prev=prev,
        action=_action,
    )


def deactivate_rule(conn: sqlite3.Connection, user_id: int, rule_id: int) -> RecurringRule:
    return update_rule(conn, user_id, rule_id, PatchRecurringRule(active=False))


def soft_delete_rule(conn: sqlite3.Connection, user_id: int, rule_id: int) -> None:
    prev = find_rule(conn, user_id, rule_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE recurring_rules SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
            (rule_id, user_id),
        )
        return rule_id, None

    mutate(
        conn,
        entity_type="recurring_rule",
        operation="delete",
        prev=prev,
        action=_action,
    )


# ---------------------------------------------------------------------------
# Overrides — FK-scoped to recurring_rules.user_id (ADR-0061 §2).
# Every query joins through `recurring_rules` so a leaked rule_id from a
# different user still filters out.
# ---------------------------------------------------------------------------


def list_overrides(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    include_consumed: bool = False,
) -> list[RecurringOverride]:
    """List overrides for a rule (FK-scoped via recurring_rules.user_id)."""
    cols = ", ".join(f"o.{c}" for c in _OVERRIDE_COLUMNS.split(", "))
    sql = (
        f"SELECT {cols} FROM recurring_rule_overrides o "
        "JOIN recurring_rules r ON r.id = o.rule_id "
        "WHERE o.rule_id = ? AND r.user_id = ?"
    )
    if not include_consumed:
        sql += " AND o.promoted_to_txn_id IS NULL"
    sql += " ORDER BY o.occurrence_date ASC"
    rows = conn.execute(sql, (rule_id, user_id)).fetchall()
    return [_row_to_override(r) for r in rows]


def list_overrides_all(
    conn: sqlite3.Connection, user_id: int, rule_id: int
) -> list[RecurringOverride]:
    """List every override for a rule, consumed or not (ADR-0046)."""
    return list_overrides(conn, user_id, rule_id, include_consumed=True)


def mark_override_promoted(
    conn: sqlite3.Connection,
    user_id: int,
    override_id: int,
    *,
    txn_id: int,
) -> None:
    """Stamp ``promoted_to_txn_id = txn_id`` on an override (ADR-0046 step 6e).

    FK-scoped: the UPDATE joins through ``recurring_rules.user_id`` so a
    leaked override id for a different user is a no-op.
    """
    conn.execute(
        "UPDATE recurring_rule_overrides AS o "
        "SET promoted_to_txn_id = ? "
        "WHERE o.id = ? "
        "AND EXISTS (SELECT 1 FROM recurring_rules r "
        "            WHERE r.id = o.rule_id AND r.user_id = ?)",
        (txn_id, override_id, user_id),
    )


def upsert_override(
    conn: sqlite3.Connection, user_id: int, data: NewRecurringOverride
) -> RecurringOverride:
    cols = ", ".join(f"o.{c}" for c in _OVERRIDE_COLUMNS.split(", "))
    existing = conn.execute(
        f"SELECT {cols} FROM recurring_rule_overrides o "
        "JOIN recurring_rules r ON r.id = o.rule_id "
        "WHERE o.rule_id = ? AND o.occurrence_date = ? AND r.user_id = ?",
        (data.rule_id, data.occurrence_date.isoformat(), user_id),
    ).fetchone()
    prev = _row_to_override(existing) if existing is not None else None

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringOverride]:
        if existing is None:
            # Insert validates ownership first via a FK-scoped lookup on the
            # parent rule — if the caller's user_id does not own rule_id the
            # lookup returns NULL and the insert aborts via the assertion.
            parent = c.execute(
                "SELECT 1 FROM recurring_rules WHERE id = ? AND user_id = ?",
                (data.rule_id, user_id),
            ).fetchone()
            if parent is None:
                raise LookupError(f"recurring_rule {data.rule_id} not owned by user {user_id}")
            cursor = c.execute(
                "INSERT INTO recurring_rule_overrides("
                "rule_id, occurrence_date, state, amount_override, "
                "description_override, date_override) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    data.rule_id,
                    data.occurrence_date.isoformat(),
                    data.state.value,
                    data.amount_override,
                    data.description_override,
                    data.date_override.isoformat() if data.date_override else None,
                ),
            )
            new_id = int(cursor.lastrowid or 0)
        else:
            new_id = int(existing["id"])
            c.execute(
                "UPDATE recurring_rule_overrides AS o "
                "SET state = ?, amount_override = ?, "
                "description_override = ?, date_override = ? "
                "WHERE o.id = ? "
                "AND EXISTS (SELECT 1 FROM recurring_rules r "
                "            WHERE r.id = o.rule_id AND r.user_id = ?)",
                (
                    data.state.value,
                    data.amount_override,
                    data.description_override,
                    data.date_override.isoformat() if data.date_override else None,
                    new_id,
                    user_id,
                ),
            )
        row = conn.execute(
            f"SELECT {cols} FROM recurring_rule_overrides o "
            "JOIN recurring_rules r ON r.id = o.rule_id "
            "WHERE o.id = ? AND r.user_id = ?",
            (new_id, user_id),
        ).fetchone()
        return new_id, _row_to_override(row)

    return mutate(
        conn,
        entity_type="recurring_override",
        operation="update" if prev is not None else "create",
        prev=prev,
        action=_action,
    )


def delete_override(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    occurrence_date: date,
) -> None:
    cols = ", ".join(f"o.{c}" for c in _OVERRIDE_COLUMNS.split(", "))
    existing = conn.execute(
        f"SELECT {cols} FROM recurring_rule_overrides o "
        "JOIN recurring_rules r ON r.id = o.rule_id "
        "WHERE o.rule_id = ? AND o.occurrence_date = ? AND r.user_id = ?",
        (rule_id, occurrence_date.isoformat(), user_id),
    ).fetchone()
    if existing is None:
        return
    prev = _row_to_override(existing)

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "DELETE FROM recurring_rule_overrides AS o "
            "WHERE o.id = ? "
            "AND EXISTS (SELECT 1 FROM recurring_rules r "
            "            WHERE r.id = o.rule_id AND r.user_id = ?)",
            (prev.id, user_id),
        )
        return prev.id, None

    mutate(
        conn,
        entity_type="recurring_override",
        operation="delete",
        prev=prev,
        action=_action,
    )


__all__ = [
    "create_rule",
    "deactivate_rule",
    "delete_override",
    "find_rule",
    "list_overrides",
    "list_overrides_all",
    "list_rules",
    "mark_override_promoted",
    "set_inactive",
    "set_next_due",
    "soft_delete_rule",
    "update_rule",
    "upsert_override",
]
