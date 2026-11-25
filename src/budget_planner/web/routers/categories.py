"""Categories router (T-033; archive + restore per T-R44, ADR-0056 §6)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.errors import require_present
from budget_planner.services import categories as categories_service
from budget_planner.services.category_forms import parse_category_patch, parse_new_category
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.dialogs import (
    MODAL_ROOT,
    dialog_response,
    invalid_dialog_response,
    saved_response,
)
from budget_planner.web.htmx import Event, toast_payload, trigger
from budget_planner.web.http_headers import HTML_MEDIA_TYPE, HX_REFRESH, HX_RESWAP
from budget_planner.web.paths import NEW_PATH
from budget_planner.web.settings_view import (
    category_form_view,
    category_not_found,
    category_row_view,
)
from budget_planner.web.view_models import category_usage_text

router = APIRouter(prefix="/categories", tags=["categories"])


_DIALOG = "pages/settings/category-dialog.html"
_ARCHIVE_DIALOG = "pages/settings/archive-category.html"
_ROW = "fragments/rows/category-row.html"


@router.get(NEW_PATH, response_class=HTMLResponse)
def new_form(request: Request) -> HTMLResponse:
    return dialog_response(
        request,
        _DIALOG,
        {
            "category": None,
            "form": category_form_view(None),
            "action": "/categories",
            "target": MODAL_ROOT,
            "errors": {},
        },
    )


@router.post("")
def create_category(
    request: Request,
    *,
    name: str = Form(...),
    direction: str = Form(...),
    color: str | None = Form(None),
    clear_color: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    parsed = parse_new_category(
        name=name, direction=direction, color=color, clear_color=clear_color
    )
    if parsed.command is None:
        return invalid_dialog_response(
            request,
            _DIALOG,
            {
                "category": None,
                "form": category_form_view(None, name=name, direction=direction, color=color),
                "action": "/categories",
                "target": MODAL_ROOT,
            },
            parsed.errors,
        )
    cat = categories_service.create(conn, user_id, parsed.command)
    response = saved_response(
        request,
        _ROW,
        {"row": category_row_view(cat)},
        message="Category created",
        events=(Event.BUDGET_STALE,),
    )
    # T-D150: the page list has no region that refetches on this trigger, so skip the swap and
    # reload to show the new item.
    response.headers[HX_RESWAP] = "none"
    response.headers[HX_REFRESH] = "true"
    return response


@router.get("/{category_id}/edit", response_class=HTMLResponse)
def edit_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return category_not_found()
    usage = categories_service.usage_for(conn, user_id, category_id)
    return dialog_response(
        request,
        _DIALOG,
        {
            "category": cat,
            "form": category_form_view(cat, usage_text=category_usage_text(usage)),
            "action": f"/categories/{category_id}",
            "target": f"#category-{category_id}",
            "errors": {},
        },
    )


@router.get("/{category_id}/archive", response_class=HTMLResponse)
def archive_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return category_not_found()
    usage = categories_service.usage_for(conn, user_id, category_id)
    return dialog_response(
        request,
        _ARCHIVE_DIALOG,
        {
            "title": f"Archive {cat.name}?",
            "post_url": f"/categories/{category_id}/archive",
            "usage_text": category_usage_text(usage),
        },
    )


@router.post("/{category_id}")
def update_category(
    category_id: int,
    request: Request,
    *,
    name: str = Form(...),
    color: str | None = Form(None),
    clear_color: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return category_not_found()
    parsed = parse_category_patch(name=name, color=color, clear_color=clear_color)
    if parsed.patch is None:
        usage = categories_service.usage_for(conn, user_id, category_id)
        return invalid_dialog_response(
            request,
            _DIALOG,
            {
                "category": cat,
                "form": category_form_view(
                    cat, name=name, color=color, usage_text=category_usage_text(usage)
                ),
                "action": f"/categories/{category_id}",
                "target": f"#category-{category_id}",
            },
            parsed.errors,
        )
    categories_service.update(conn, user_id, category_id, parsed.patch)
    updated = require_present(
        categories_service.find_by_id(conn, user_id, category_id), "updated category"
    )
    return saved_response(
        request,
        _ROW,
        {"row": category_row_view(updated)},
        message="Category saved",
        events=(Event.BUDGET_STALE,),
    )


@router.post("/{category_id}/delete")
def delete_category(
    category_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    if cat.is_system:
        return Response(status_code=409, content="system categories cannot be deleted")
    categories_service.soft_delete(conn, user_id, category_id)
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.BUDGET_STALE)
    return resp


# ---------------------------------------------------------------------------
# T-R44 — Archive + Restore (ADR-0056 §6, ADR-0022 soft delete, ADR-0019 audit)
# ---------------------------------------------------------------------------
@router.post("/{category_id}/archive")
def archive_category(
    category_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    try:
        categories_service.archive(conn, user_id, category_id)
    except categories_service.CategoryNotFoundError:
        return Response(status_code=404, content="not found")
    except categories_service.SystemCategoryError:
        return Response(status_code=403, content="system categories cannot be archived")
    except categories_service.CategoryHasLiveRulesError as exc:
        blocked = Response(status_code=422, content=str(exc))
        blocked.headers[HX_RESWAP] = "none"
        trigger(blocked, toast=toast_payload("error", str(exc)))
        return blocked
    resp = Response(status_code=204)
    trigger(
        resp,
        Event.DIALOG_CLOSE,
        Event.SETTINGS_CATEGORIES_STALE,
        Event.BUDGET_STALE,
        toast=toast_payload(
            "success", "Category archived", undo_url=f"/categories/{category_id}/restore"
        ),
    )
    return resp


@router.post("/{category_id}/restore")
def restore_category(
    category_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    try:
        categories_service.restore(conn, user_id, category_id)
    except categories_service.CategoryNotFoundError:
        return Response(status_code=404, content="not found")
    resp = Response(status_code=204)
    trigger(
        resp,
        Event.SETTINGS_CATEGORIES_STALE,
        Event.BUDGET_STALE,
        toast=toast_payload("success", "Category restored"),
    )
    return resp
