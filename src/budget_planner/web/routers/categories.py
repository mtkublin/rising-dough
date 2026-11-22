"""Categories router (T-033; archive + restore per T-R44, ADR-0056 §6)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.errors import require_present
from budget_planner.services import categories as categories_service
from budget_planner.services.category_forms import parse_category_patch, parse_new_category
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.htmx import Event, toast_payload, trigger
from budget_planner.web.http_headers import HTML_MEDIA_TYPE, HX_REFRESH, HX_RESWAP
from budget_planner.web.paths import NEW_PATH
from budget_planner.web.rendering import SLIDEOVER_TEMPLATE, render

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get(NEW_PATH, response_class=HTMLResponse)
def new_form(request: Request) -> HTMLResponse:
    return render(
        request,
        SLIDEOVER_TEMPLATE,
        slide_over_title="New category",
        form_include="partials/categories/_form.html",
        category=None,
        action="/categories",
        errors={},
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
        return render(
            request,
            "partials/categories/_form.html",
            category=None,
            action="/categories",
            errors=parsed.errors,
            status_code=422,
        )
    cat = categories_service.create(conn, user_id, parsed.command)
    html = render(request, "partials/categories/_row.html", category=cat)
    trigger(html, Event.BUDGET_STALE)
    # T-D150: the form targets itself and the categories list has no region that
    # refetches on a trigger, so skip the swap and reload to show the new item.
    html.headers[HX_RESWAP] = "none"
    html.headers[HX_REFRESH] = "true"
    return html


@router.get("/{category_id}/edit", response_class=HTMLResponse)
def edit_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return render(
            request,
            "partials/categories/_form.html",
            category=None,
            action="",
            errors={"category": "not found"},
            status_code=404,
        )
    return render(
        request,
        SLIDEOVER_TEMPLATE,
        slide_over_title="Edit category",
        form_include="partials/categories/_form.html",
        category=cat,
        action=f"/categories/{category_id}",
        errors={},
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
        return render(
            request,
            "partials/categories/_form.html",
            category=None,
            action="",
            errors={"category": "not found"},
            status_code=404,
        )
    parsed = parse_category_patch(name=name, color=color, clear_color=clear_color)
    if parsed.patch is None:
        return render(
            request,
            "partials/categories/_form.html",
            category=cat,
            action=f"/categories/{category_id}",
            errors=parsed.errors,
            status_code=422,
        )
    categories_service.update(conn, user_id, category_id, parsed.patch)
    updated = require_present(
        categories_service.find_by_id(conn, user_id, category_id), "updated category"
    )
    html = render(request, "partials/categories/_row.html", category=updated)
    trigger(html, Event.BUDGET_STALE)
    return html


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
        return Response(status_code=422, content=str(exc))
    resp = Response(status_code=204)
    trigger(
        resp,
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
