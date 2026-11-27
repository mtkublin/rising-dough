"""Category dialog 422 re-renders (T-UR00b): the dialog again with its field errors.

Shared by the create and edit routes so each handler stays small (G25).
"""

from __future__ import annotations

import sqlite3

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.errors import ValidationError
from budget_planner.services import categories as categories_service
from budget_planner.services.category_forms import parse_new_category
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


_PICKER_CREATED = "fragments/fields/category-picker-created.html"
_PICKER_ERROR = "fragments/fields/category-picker-error.html"


def create_from_picker(
    request: Request, conn: sqlite3.Connection, user_id: int, *, name: str
) -> Response:
    """Create an expense category from the entry dialog's picker (T-UR68).

    200: the new list option (combobox.js inserts and picks it). 422: the field error line for
    the picker's empty block. The entry dialog is never replaced either way.
    """
    parsed = parse_new_category(
        name=name, direction=Direction.EXPENSE.value, color=None, clear_color=None
    )
    errors = parsed.errors
    created = None
    if parsed.command is not None:
        try:
            created = categories_service.create(conn, user_id, parsed.command)
        except ValidationError as exc:
            errors = exc.fields
    env = request.app.state.jinja_env
    ctx = {"request": request, "csp_nonce": getattr(request.state, "csp_nonce", "")}
    if created is None:
        message = next(iter(errors.values()), "invalid category")
        body = env.get_template(_PICKER_ERROR).render(**ctx, message=message)
        return HTMLResponse(body, status_code=422)
    return HTMLResponse(env.get_template(_PICKER_CREATED).render(**ctx, category=created))
