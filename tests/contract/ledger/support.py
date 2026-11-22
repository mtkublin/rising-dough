"""Helpers shared by the ledger-surface contract tests (T-UT04c)."""

from __future__ import annotations

import json
from typing import Any

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection

USER_ID = 1


def query(settings: Settings, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """Read-only helper against the test's temp DB."""
    conn = get_connection(settings)
    try:
        return list(conn.execute(sql, params).fetchall())
    finally:
        conn.close()


def scalar(settings: Settings, sql: str, params: tuple[Any, ...] = ()) -> Any:
    return query(settings, sql, params)[0][0]


def audit_ops(settings: Settings, entity_type: str, entity_id: int) -> list[str]:
    """Operations recorded in ``audit_log`` for one entity, oldest first."""
    rows = query(
        settings,
        "SELECT operation FROM audit_log WHERE entity_type = ? AND entity_id = ? ORDER BY id",
        (entity_type, entity_id),
    )
    return [r[0] for r in rows]


def hx_events(response: Any) -> dict[str, Any]:
    """Parsed ``HX-Trigger`` payload ({} when absent)."""
    raw = response.headers.get("HX-Trigger")
    return json.loads(raw) if raw else {}


def txn_form(seeded: dict[str, int], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "operation_date": "2026-10-20",
        "category_id": seeded["exp"],
        "account_id": seeded["acc"],
        "amount": "12.34",
        "description": "contract",
    }
    return {**base, **overrides}


def rule_form(seeded: dict[str, int], **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "cadence": "monthly",
        "start_date": "2026-02-01",
        "category_id": seeded["exp"],
        "account_id": seeded["acc"],
        "default_amount": "500",
        "default_description": "contract rule",
    }
    return {**base, **overrides}
