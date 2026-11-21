"""Row, audit and form helpers for the T-UT04e settings contract tests."""

from __future__ import annotations

import sqlite3
from typing import Any

from bs4 import Tag

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import categories as categories_repo
from tests.ui_map import _html
from tests.ui_map.locator import Locator

USER_ID = 1
HX = {"HX-Request": "true"}
_CONTROLS = frozenset({"input", "select", "textarea"})


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


def make_category(settings: Settings, name: str = "Groceries") -> int:
    conn = get_connection(settings)
    try:
        return categories_repo.create(
            conn, USER_ID, NewCategory(name=name, direction=Direction.EXPENSE)
        ).id
    finally:
        conn.close()


def system_category_id(settings: Settings, *, name: str) -> int:
    conn = get_connection(settings)
    try:
        cat = categories_repo.find_by_name(conn, USER_ID, name)
    finally:
        conn.close()
    assert cat is not None
    return cat.id


def field(html: str, label_loc: Locator) -> Tag:
    """The single form control a ``label`` locator names."""
    controls = [el for el in _html.resolve(html, label_loc) if el.name in _CONTROLS]
    if len(controls) != 1:
        raise LookupError(f"expected one control for {label_loc!r}, found {len(controls)}")
    return controls[0]


def live_sessions(db: sqlite3.Connection, user_id: int) -> int:
    row = db.execute(
        "SELECT count(*) FROM sessions WHERE user_id = ? AND revoked_at IS NULL", (user_id,)
    ).fetchone()
    return int(row[0])
