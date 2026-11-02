"""Recurring rules + sparse overrides repository (ADR-0013 / ADR-0038 / ADR-0045)."""

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
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required
from budget_planner.services.recurring import first_due_on_or_after

_RULE_COLUMNS = (
    "id, user_id, cadence, start_date, end_date, category_id, account_id, "
    "dest_account_id, default_amount, default_description, day_of_month, "
    "month_of_year, active, next_due, last_promoted_date, amount_formula, "
    "created_at, updated_at, deleted_at"
)


def _formula_to_json(formula: AmountFormula | None) -> str | None:
    """Serialise `AmountFormula` to v2 JSON (ADR-0047).

    Future tier-B/C upgrades bump `schema_version` and extend this
    serialiser; the inverse `_formula_from_json` dispatches on version.
    """
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
    """Parse `recurring_rules.amount_formula` JSON into `AmountFormula`.

    Dispatches on `schema_version`:
    - v1 (legacy, pre-migration-0010): wrapped on the fly as a single
      positive-sign term so the service layer never sees v1 shape.
    - v2 (current): straightforward terms-list unmarshal.

    v1 fallback is defensive; migration 0010 rewrites every live row to v2
    on `just migrate`. Tests exercise both branches.
    """
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


def _compute_initial_next_due(data: NewRecurringRule, today: date) -> date:
    """Return the earliest canonical occurrence on-or-after ``max(start, today)``.

    Delegates to the pure helper ``services.recurring.first_due_on_or_after``
    (T-118). End-date guard: if the rule's ``end_date`` has already passed
    the helper still returns ``start_date`` as a sentinel; the caller is
    responsible for toggling ``active=False`` in that terminal case.
    """
    stub = RecurringRule(
        id=0,
        user_id=data.user_id,
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
    rule_id: int,
    *,
    include_deleted: bool = False,
) -> RecurringRule | None:
    sql = f"SELECT {_RULE_COLUMNS} FROM recurring_rules WHERE id = ?"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    row = conn.execute(sql, (rule_id,)).fetchone()
    return _row_to_rule(row) if row is not None else None


def list_rules(
    conn: sqlite3.Connection,
    *,
    active_only: bool = False,
    include_deleted: bool = False,
) -> list[RecurringRule]:
    sql = f"SELECT {_RULE_COLUMNS} FROM recurring_rules"
    clauses: list[str] = []
    if active_only:
        clauses.append("active = 1")
    if not include_deleted:
        clauses.append("deleted_at IS NULL")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY start_date ASC, id ASC"
    return [_row_to_rule(r) for r in conn.execute(sql).fetchall()]


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


def create_rule(conn: sqlite3.Connection, data: NewRecurringRule) -> RecurringRule:
    today = dt.date.today()  # noqa: DTZ011 — date-only anchor; display tz applies at render
    initial_next_due = _compute_initial_next_due(data, today)

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringRule]:
        cursor = c.execute(
            "INSERT INTO recurring_rules("
            "user_id, cadence, start_date, end_date, category_id, account_id, "
            "dest_account_id, default_amount, default_description, "
            "day_of_month, month_of_year, active, next_due, amount_formula) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                data.user_id,
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
        created = find_rule(c, new_id)
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
    rule_id: int,
    *,
    next_due: date,
    last_promoted_date: date | None,
) -> None:
    """Thin helper for the T-118 promotion service.

    Audit-free: the orchestrating service is responsible for writing a
    paired audit entry via `services.audit.record` after calling this
    helper. Keeping the write audit-free here lets the service compose
    multiple repository calls (txn insert + rule advance + override
    delete) under a single audit row.
    """
    conn.execute(
        "UPDATE recurring_rules SET next_due = ?, last_promoted_date = ?, "
        "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
        "WHERE id = ?",
        (
            next_due.isoformat(),
            last_promoted_date.isoformat() if last_promoted_date is not None else None,
            rule_id,
        ),
    )


def set_inactive(conn: sqlite3.Connection, rule_id: int) -> None:
    """Thin helper for the T-118 promotion service — mark a rule inactive.

    Audit-free; the service writes the paired audit entry (see
    `set_next_due`). Idempotent: setting an already-inactive rule inactive
    is a no-op.
    """
    conn.execute(
        "UPDATE recurring_rules SET active = 0, "
        "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
        "WHERE id = ?",
        (rule_id,),
    )


def update_rule(
    conn: sqlite3.Connection,
    rule_id: int,
    data: PatchRecurringRule,
) -> RecurringRule:
    prev = find_rule(conn, rule_id, include_deleted=True)
    if prev is None:
        raise LookupError(f"recurring_rule {rule_id} not found")
    changes = _normalise_rule_patch(data.as_dict())

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringRule]:
        if changes:
            sets = [f"{field} = ?" for field in changes]
            sets.append("updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))")
            c.execute(
                f"UPDATE recurring_rules SET {', '.join(sets)} WHERE id = ?",
                (*changes.values(), rule_id),
            )
        updated = find_rule(c, rule_id, include_deleted=True)
        assert updated is not None
        return rule_id, updated

    return mutate(
        conn,
        entity_type="recurring_rule",
        operation="update",
        prev=prev,
        action=_action,
    )


def deactivate_rule(conn: sqlite3.Connection, rule_id: int) -> RecurringRule:
    return update_rule(conn, rule_id, PatchRecurringRule(active=False))


def soft_delete_rule(conn: sqlite3.Connection, rule_id: int) -> None:
    prev = find_rule(conn, rule_id)
    if prev is None:
        return

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "UPDATE recurring_rules SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')), "
            "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
            "WHERE id = ? AND deleted_at IS NULL",
            (rule_id,),
        )
        return rule_id, None

    mutate(
        conn,
        entity_type="recurring_rule",
        operation="delete",
        prev=prev,
        action=_action,
    )


def list_overrides(
    conn: sqlite3.Connection,
    rule_id: int,
    *,
    include_consumed: bool = False,
) -> list[RecurringOverride]:
    """List overrides for a rule.

    Default excludes consumed overrides (ADR-0046) so pre-ADR-0046 callers
    (promote lookup, override UI, skip-and-advance) see only live rows.
    Formula compute paths (ADR-0045) call ``list_overrides_all`` to include
    historical rows that still need to materialise their canonical month.
    """
    sql = f"SELECT {_OVERRIDE_COLUMNS} FROM recurring_rule_overrides WHERE rule_id = ?"
    if not include_consumed:
        sql += " AND promoted_to_txn_id IS NULL"
    sql += " ORDER BY occurrence_date ASC"
    rows = conn.execute(sql, (rule_id,)).fetchall()
    return [_row_to_override(r) for r in rows]


def list_overrides_all(conn: sqlite3.Connection, rule_id: int) -> list[RecurringOverride]:
    """List every override for a rule, consumed or not (ADR-0046)."""
    return list_overrides(conn, rule_id, include_consumed=True)


def mark_override_promoted(
    conn: sqlite3.Connection,
    override_id: int,
    *,
    txn_id: int,
) -> None:
    """Stamp ``promoted_to_txn_id = txn_id`` on an override (ADR-0046 step 6e).

    Audit-free: the orchestrating promotion service writes a single
    ``update`` audit entry on the rule mutation, matching the pattern used
    by ``set_next_due`` / ``set_inactive``.
    """
    conn.execute(
        "UPDATE recurring_rule_overrides SET promoted_to_txn_id = ? WHERE id = ?",
        (txn_id, override_id),
    )


def upsert_override(conn: sqlite3.Connection, data: NewRecurringOverride) -> RecurringOverride:
    existing = conn.execute(
        f"SELECT {_OVERRIDE_COLUMNS} FROM recurring_rule_overrides "
        "WHERE rule_id = ? AND occurrence_date = ?",
        (data.rule_id, data.occurrence_date.isoformat()),
    ).fetchone()
    prev = _row_to_override(existing) if existing is not None else None

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringOverride]:
        if existing is None:
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
                "UPDATE recurring_rule_overrides SET state = ?, amount_override = ?, "
                "description_override = ?, date_override = ? WHERE id = ?",
                (
                    data.state.value,
                    data.amount_override,
                    data.description_override,
                    data.date_override.isoformat() if data.date_override else None,
                    new_id,
                ),
            )
        row = conn.execute(
            f"SELECT {_OVERRIDE_COLUMNS} FROM recurring_rule_overrides WHERE id = ?",
            (new_id,),
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
    rule_id: int,
    occurrence_date: date,
) -> None:
    existing = conn.execute(
        f"SELECT {_OVERRIDE_COLUMNS} FROM recurring_rule_overrides "
        "WHERE rule_id = ? AND occurrence_date = ?",
        (rule_id, occurrence_date.isoformat()),
    ).fetchone()
    if existing is None:
        return
    prev = _row_to_override(existing)

    def _action(c: sqlite3.Connection) -> tuple[int, None]:
        c.execute(
            "DELETE FROM recurring_rule_overrides WHERE id = ?",
            (prev.id,),
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
