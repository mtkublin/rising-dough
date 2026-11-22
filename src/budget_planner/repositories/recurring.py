"""Recurring rules + sparse overrides repository (ADR-0013 / ADR-0038 / ADR-0045).

## User-scoping discipline (T-D16 / ADR-0061 §5)

Every rule-level function takes ``user_id`` as the first positional arg after
``conn``; every SELECT / UPDATE / DELETE on ``recurring_rules`` carries
``user_id = :user_id``. Override queries scope through the parent
``recurring_rules.user_id`` via FK join predicate — see ADR-0061 §2. The
``tests/architecture/test_user_id_filter.py`` static test backstops the rule.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any, cast

from budget_planner import clock
from budget_planner.config import get_settings
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
from budget_planner.domain.recurring_schedule import initial_next_due as compute_initial_next_due
from budget_planner.repositories._shared import mutate, parse_dt, parse_dt_required, require_owned

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


def _normalise_patch_value(key: str, value: object) -> object:
    """Encode one patched rule field for storage."""
    if key == "cadence":
        return cast(Cadence, value).value
    if key in {"start_date", "next_due"} and value is not None:
        return cast(date, value).isoformat()
    if key == "end_date":
        # end_date is sentinel-nullable (ADR-0063). The caller may clear
        # it by patching with None.
        return cast(date, value).isoformat() if value is not None else None
    if key == "active":
        return int(bool(value))
    if key == "amount_formula":
        return _formula_to_json(cast("AmountFormula | None", value))
    return value


def _normalise_rule_patch(changes: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalise_patch_value(key, value) for key, value in changes.items()}


def create_rule(conn: sqlite3.Connection, user_id: int, data: NewRecurringRule) -> RecurringRule:
    require_owned(
        conn,
        user_id,
        account_ids=(data.account_id, data.dest_account_id),
        category_ids=(data.category_id,),
    )
    today = clock.today_local(get_settings())
    first_due = compute_initial_next_due(data, user_id, today)

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
                first_due.isoformat(),
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
        user_id=user_id,
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
        user_id=user_id,
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
        user_id=user_id,
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
        "WHERE o.rule_id = ? AND r.user_id = ? AND r.deleted_at IS NULL"
    )
    if not include_consumed:
        sql += " AND o.promoted_to_txn_id IS NULL"
    sql += " ORDER BY o.occurrence_date ASC"
    rows = conn.execute(sql, (rule_id, user_id)).fetchall()
    return [_row_to_override(r) for r in rows]


def list_pending_overrides_by_rule(
    conn: sqlite3.Connection, user_id: int
) -> dict[int, list[RecurringOverride]]:
    """Unconsumed overrides of every live rule in one query, keyed by ``rule_id`` (T-Q234)."""
    cols = ", ".join(f"o.{c}" for c in _OVERRIDE_COLUMNS.split(", "))
    rows = conn.execute(
        f"SELECT {cols} FROM recurring_rule_overrides o "
        "JOIN recurring_rules r ON r.id = o.rule_id "
        "WHERE r.user_id = ? AND r.deleted_at IS NULL AND o.promoted_to_txn_id IS NULL "
        "ORDER BY o.occurrence_date ASC",
        (user_id,),
    ).fetchall()
    out: dict[int, list[RecurringOverride]] = {}
    for row in rows:
        override = _row_to_override(row)
        out.setdefault(override.rule_id, []).append(override)
    return out


def list_overrides_all(
    conn: sqlite3.Connection, user_id: int, rule_id: int
) -> list[RecurringOverride]:
    """List every override for a rule, consumed or not (ADR-0046)."""
    return list_overrides(conn, user_id, rule_id, include_consumed=True)


def _find_override_row(
    conn: sqlite3.Connection, user_id: int, where: str, params: tuple[object, ...]
) -> sqlite3.Row | None:
    """One override row of a live rule owned by ``user_id`` (``where`` filters ``o`` columns)."""
    cols = ", ".join(f"o.{c}" for c in _OVERRIDE_COLUMNS.split(", "))
    row: sqlite3.Row | None = conn.execute(
        f"SELECT {cols} FROM recurring_rule_overrides o "
        "JOIN recurring_rules r ON r.id = o.rule_id "
        f"WHERE {where} AND r.user_id = ? AND r.deleted_at IS NULL",
        (*params, user_id),
    ).fetchone()
    return row


def _require_owned_rule(c: sqlite3.Connection, user_id: int, rule_id: int) -> None:
    """Refuse an insert unless the caller owns the live parent rule."""
    parent = c.execute(
        "SELECT 1 FROM recurring_rules WHERE id = ? AND user_id = ? AND deleted_at IS NULL",
        (rule_id, user_id),
    ).fetchone()
    if parent is None:
        raise LookupError(f"recurring_rule {rule_id} not owned by user {user_id}")


def _override_payload(data: NewRecurringOverride) -> tuple[str, int | None, str | None, str | None]:
    """The mutable columns (state, amount, description, date) in storage form."""
    date_override = data.date_override.isoformat() if data.date_override else None
    return data.state.value, data.amount_override, data.description_override, date_override


def upsert_override(
    conn: sqlite3.Connection, user_id: int, data: NewRecurringOverride
) -> RecurringOverride:
    existing = _find_override_row(
        conn,
        user_id,
        "o.rule_id = ? AND o.occurrence_date = ?",
        (data.rule_id, data.occurrence_date.isoformat()),
    )
    prev = _row_to_override(existing) if existing is not None else None

    def _action(c: sqlite3.Connection) -> tuple[int, RecurringOverride]:
        if existing is None:
            _require_owned_rule(c, user_id, data.rule_id)
            cursor = c.execute(
                "INSERT INTO recurring_rule_overrides("
                "rule_id, occurrence_date, state, amount_override, "
                "description_override, date_override) VALUES (?, ?, ?, ?, ?, ?)",
                (data.rule_id, data.occurrence_date.isoformat(), *_override_payload(data)),
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
                (*_override_payload(data), new_id, user_id),
            )
        written = cast(sqlite3.Row, _find_override_row(conn, user_id, "o.id = ?", (new_id,)))
        return new_id, _row_to_override(written)

    return mutate(
        conn,
        entity_type="recurring_override",
        operation="update" if prev is not None else "create",
        prev=prev,
        action=_action,
        user_id=user_id,
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
        "WHERE o.rule_id = ? AND o.occurrence_date = ? AND r.user_id = ? "
        "AND r.deleted_at IS NULL",
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
        user_id=user_id,
    )


__all__ = [
    "create_rule",
    "deactivate_rule",
    "delete_override",
    "find_rule",
    "list_overrides",
    "list_overrides_all",
    "list_rules",
    "soft_delete_rule",
    "update_rule",
    "upsert_override",
]
