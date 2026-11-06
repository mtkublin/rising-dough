"""Categories router (T-033; archive + restore per T-R44, ADR-0056 §6)."""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.domain.categories import NewCategory, PatchCategory, normalise_color
from budget_planner.domain.enums import Direction
from budget_planner.repositories import categories as categories_repo
from budget_planner.services import categories as categories_service
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.htmx import trigger
from budget_planner.web.rendering import render

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
def index() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the Settings drawer's Categories tab. The CRUD sub-routes
    (``/categories/new``, ``/categories/{id}/edit``, etc.) remain live
    because the Settings drawer reuses them as HTMX fragments.
    """
    return RedirectResponse(url="/settings?tab=categories", status_code=302)


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request) -> HTMLResponse:
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="New category",
        form_include="partials/categories/_form.html",
        category=None,
        action="/categories",
        errors={},
    )


_USER_DIRECTIONS: frozenset[Direction] = frozenset({Direction.INCOME, Direction.EXPENSE})


def _validate_direction(value: str) -> Direction | None:
    """Return the direction only if user-pickable.

    T-115 / F1.6 — transit + adjustment are reserved for seeded system
    categories (``Transit``, ``Reconciliation``) and must not reach the
    repository via a user POST.
    """
    try:
        d = Direction(value)
    except ValueError:
        return None
    if d not in _USER_DIRECTIONS:
        return None
    return d


def _resolve_color_form(color: str | None, clear_color: str | None) -> tuple[str | None, bool]:
    """ADR-0048 — return ``(hex_or_none, clear_requested)``.

    ``clear_color`` present means "reset to direction default" and wins over
    any ``color`` value the browser might send. Raises ``ValueError`` via
    ``normalise_color`` on malformed hex.
    """
    cleared = bool(clear_color)
    if cleared:
        return None, True
    return normalise_color(color), False


@router.post("")
def create_category(  # noqa: PLR0917
    request: Request,
    name: str = Form(...),
    direction: str = Form(...),
    color: str | None = Form(None),
    clear_color: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    errors: dict[str, str] = {}
    d = _validate_direction(direction)
    if d is None:
        errors["direction"] = "invalid direction"
    if not name.strip():
        errors["name"] = "name required"
    resolved_color: str | None = None
    try:
        resolved_color, _ = _resolve_color_form(color, clear_color)
    except ValueError as exc:
        errors["color"] = str(exc)
    if errors:
        return render(
            request,
            "partials/categories/_form.html",
            category=None,
            action="/categories",
            errors=errors,
            status_code=422,
        )
    assert d is not None
    cat = categories_repo.create(
        conn, user_id, NewCategory(name=name.strip(), direction=d, color=resolved_color)
    )
    html = render(request, "partials/categories/_row.html", category=cat)
    trigger(html, "budget-stale")
    return html


@router.get("/{category_id}/edit", response_class=HTMLResponse)
def edit_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    cat = categories_repo.find_by_id(conn, user_id, category_id)
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
        "partials/_slideover.html",
        slide_over_title="Edit category",
        form_include="partials/categories/_form.html",
        category=cat,
        action=f"/categories/{category_id}",
        errors={},
    )


@router.post("/{category_id}")
def update_category(  # noqa: PLR0917
    category_id: int,
    request: Request,
    name: str = Form(...),
    color: str | None = Form(None),
    clear_color: str | None = Form(None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if cat is None:
        return render(
            request,
            "partials/categories/_form.html",
            category=None,
            action="",
            errors={"category": "not found"},
            status_code=404,
        )
    errors: dict[str, str] = {}
    if not name.strip():
        errors["name"] = "name required"
    resolved_color: str | None = None
    clear_requested = False
    try:
        resolved_color, clear_requested = _resolve_color_form(color, clear_color)
    except ValueError as exc:
        errors["color"] = str(exc)
    if errors:
        return render(
            request,
            "partials/categories/_form.html",
            category=cat,
            action=f"/categories/{category_id}",
            errors=errors,
            status_code=422,
        )
    patch = PatchCategory(
        name=name.strip(),
        color=resolved_color,
        clear_color=clear_requested,
    )
    categories_repo.update(conn, user_id, category_id, patch)
    updated = categories_repo.find_by_id(conn, user_id, category_id)
    assert updated is not None
    html = render(request, "partials/categories/_row.html", category=updated)
    trigger(html, "budget-stale")
    return html


@router.post("/{category_id}/delete")
def delete_category(
    category_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    if cat.is_system:
        return Response(status_code=409, content="system categories cannot be deleted")
    categories_repo.soft_delete(conn, user_id, category_id)
    resp = Response(content="", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


# ---------------------------------------------------------------------------
# T-R44 — Archive + Restore (ADR-0056 §6, ADR-0022 soft delete, ADR-0019 audit)
# ---------------------------------------------------------------------------
def _toast_trigger(
    resp: Response,
    *,
    message: str,
    variant: str,
    undo_url: str | None,
    stale_event: str = "settings-categories-stale",
) -> None:
    payload: dict[str, object] = {
        "toast": {"variant": variant, "message": message},
        stale_event: True,
        "budget-stale": True,
    }
    if undo_url is not None:
        toast = payload["toast"]
        assert isinstance(toast, dict)
        toast["undo_url"] = undo_url
    resp.headers["HX-Trigger"] = json.dumps(payload)


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
    _toast_trigger(
        resp,
        message="Category archived",
        variant="success",
        undo_url=f"/categories/{category_id}/restore",
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
    _toast_trigger(
        resp,
        message="Category restored",
        variant="success",
        undo_url=None,
    )
    return resp
