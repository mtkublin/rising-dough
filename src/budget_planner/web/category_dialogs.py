"""Category dialog 422 re-renders (T-UR00b): the dialog again with its field errors.

Shared by the create and edit routes so each handler stays small (G25).
"""

from __future__ import annotations

import sqlite3

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.categories import Category
from budget_planner.services import categories as categories_service
from budget_planner.web.dialogs import MODAL_ROOT, invalid_dialog_response
from budget_planner.web.paths import CATEGORIES_PATH
from budget_planner.web.settings_view import category_form_view
from budget_planner.web.view_models import category_usage_text

_DIALOG = "pages/settings/category-dialog.html"


def new_category_invalid(
    request: Request, *, name: str, direction: str, color: str | None, errors: dict[str, str]
) -> Response:
    """The new-category dialog again with ``errors`` (422)."""
    return invalid_dialog_response(
        request,
        _DIALOG,
        {
            "category": None,
            "form": category_form_view(None, name=name, direction=direction, color=color),
            "action": CATEGORIES_PATH,
            "target": MODAL_ROOT,
        },
        errors,
    )


def edit_category_invalid(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    cat: Category,
    *,
    name: str,
    color: str | None,
    errors: dict[str, str],
) -> Response:
    """The edit dialog again with ``errors`` (422)."""
    usage = categories_service.usage_for(conn, user_id, cat.id)
    return invalid_dialog_response(
        request,
        _DIALOG,
        {
            "category": cat,
            "form": category_form_view(
                cat, name=name, color=color, usage_text=category_usage_text(usage)
            ),
            "action": f"{CATEGORIES_PATH}/{cat.id}",
            "target": f"#category-{cat.id}",
        },
        errors,
    )
