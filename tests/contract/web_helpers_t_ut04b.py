"""Row, audit and form helpers for the T-UT04b contract tests."""

from __future__ import annotations

from typing import Any

from bs4 import Tag

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from tests.ui_map import _html
from tests.ui_map.locator import Locator

OTHER_USER_ID = 2


def fetch_all(settings: Settings, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    conn = get_connection(settings)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def audit_ops(settings: Settings, entity_type: str) -> list[tuple[str, int]]:
    """``(operation, entity_id)`` audit rows for ``entity_type``, oldest first."""
    rows = fetch_all(
        settings,
        "SELECT operation, entity_id FROM audit_log WHERE entity_type = ? ORDER BY id",
        (entity_type,),
    )
    return [(r["operation"], r["entity_id"]) for r in rows]


def seed_other_user(settings: Settings) -> int:
    """Insert a second user (id 2) so ownership checks have a foreign owner."""
    conn = get_connection(settings)
    try:
        conn.execute(
            "INSERT INTO users (id, name) VALUES (?, 'other') ON CONFLICT(id) DO NOTHING",
            (OTHER_USER_ID,),
        )
        conn.commit()
    finally:
        conn.close()
    return OTHER_USER_ID


def field(html: str, label_loc: Locator) -> Tag:
    """The single form control a ``label`` locator names."""
    return _html.resolve_one(html, label_loc)
