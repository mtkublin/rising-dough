"""Planned transactions router (T-034)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Final

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
)
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    export as export_service,
    planned as planned_service,
)
from budget_planner.web import entry_forms, ledger_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.htmx import Event, refresh_unless_on, toast_payload, trigger
from budget_planner.web.params import parse_date, positive_amount
from budget_planner.web.rendering import render

router = APIRouter(prefix="/planned", tags=["planned"])


_PROMOTE_EVENTS: Final = (
    Event.LEDGER_STALE,
    Event.FORECAST_STALE,
    Event.BALANCE_STALE,
    Event.TODAY_STALE,
)


# ---------------------------------------------------------------------------
# T-R45 — Batch promote-due (ADR-0056 §6, ADR-0012). Registered BEFORE
# the dynamic `/{planned_id}` paths.
# ---------------------------------------------------------------------------
@router.post("/batch/promote-due", response_class=HTMLResponse)
def planned_batch_promote_due(
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> Response:
    """Promote every unpromoted planned row with ``operation_date <= today``."""
    try:
        result = planned_service.batch_promote_due(conn, user_id, today)
    except (
        planned_service.AlreadyPromotedError,
        planned_service.CannotPromoteDeletedError,
        planned_service.UnsupportedDirectionError,
        planned_service.ValidationError,
    ) as exc:
        return Response(status_code=422, content=str(exc))
    resp = Response(status_code=204)
    trigger(
        resp,
        *_PROMOTE_EVENTS,
        toast=toast_payload(
            "success",
            f"Promoted {len(result.promoted_txn_ids)} planned row(s)",
            undo_url="/planned/batch/undo",
            undo_payload={
                "promoted_txn_ids": list(result.promoted_txn_ids),
                "promoted_planned_ids": list(result.promoted_planned_ids),
            },
        ),
    )
    return resp


@router.post("/batch/undo", response_class=HTMLResponse)
async def planned_batch_undo(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Reverse a prior batch planned promote.

    Audited action (ADR-0019 amendment, T-Q228): soft-deletes each promoted
    transaction and clears ``promoted_to_txn_id`` on each planned row that is
    still stamped with one of this batch's transactions.
    """
    form = await request.form()
    try:
        txn_ids = [int(v) for v in str(form.get("promoted_txn_ids", "")).split(",") if v]
        planned_ids = [int(v) for v in str(form.get("promoted_planned_ids", "")).split(",") if v]
    except ValueError:
        return Response(status_code=422, content="invalid id list")

    result = planned_service.undo_batch(conn, user_id, txn_ids, planned_ids)
    message = "Undone"
    if result.skipped_planned_ids:
        message = f"Undone ({len(result.skipped_planned_ids)} row(s) changed since, left as is)"
    resp = Response(status_code=204)
    trigger(resp, *_PROMOTE_EVENTS, toast=toast_payload("info", message))
    return resp


@router.get("/table", response_class=HTMLResponse)
def table_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    """Legacy fragment alias (T-064).

    Delegates to the unified ledger fragment with ``view=planned``.
    """
    return ledger_data.render_table_for(
        request, conn, user_id, settings=settings, view="planned", today=today
    )


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    # T-069 — slide-over wrapper for FAB launches.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="New planned transaction",
        form_include="partials/planned/_form.html",
        planned=None,
        action="/planned",
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors={},
    )


@router.post("")
def create_planned(
    request: Request,
    *,
    operation_date: str = Form(...),
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    dest_account_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    check = entry_forms.check_planned_create(
        conn,
        user_id,
        operation_date=operation_date,
        category_id=category_id,
        account_id=account_id,
        amount=amount,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return render(
            request,
            "partials/planned/_form.html",
            planned=None,
            action="/planned",
            categories=categories_service.list_all(conn, user_id),
            accounts=accounts_service.list_all(conn, user_id),
            errors=check.errors,
            status_code=422,
        )
    assert check.op_date is not None and check.minor is not None
    pl = planned_service.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=check.op_date,
            category_id=category_id,
            account_id=account_id,
            amount=check.minor,
            description=description,
            dest_account_id=check.dest_id,
        ),
    )
    view = ledger_data.planned_row_from_persisted(pl, check.account, check.category)
    html = render(request, "partials/planned/_row.html", view=view)
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    # The form is hosted by every page's overlay: no row insert; the ledger
    # refetches on `ledger-stale`, other pages reload (T-D142).
    refresh_unless_on(request, html, "/ledger")
    return html


@router.get("/{planned_id}/edit", response_class=HTMLResponse)
def edit_form(
    planned_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return render(
            request,
            "partials/planned/_form.html",
            planned=None,
            action="",
            categories=[],
            accounts=[],
            errors={"planned": "not found"},
            status_code=404,
        )
    # T-114 / ADR-0030 §4 — slide-over wrapper mirrors /planned/new.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="Edit planned transaction",
        form_include="partials/planned/_form.html",
        planned=pl,
        action=f"/planned/{planned_id}",
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors={},
    )


@router.post("/{planned_id}")
def update_planned(
    planned_id: int,
    request: Request,
    *,
    operation_date: str = Form(...),
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    dest_account_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    check = entry_forms.check_planned_update(
        conn,
        user_id,
        existing_dest_id=pl.dest_account_id,
        operation_date=operation_date,
        category_id=category_id,
        account_id=account_id,
        amount=amount,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return render(
            request,
            "partials/planned/_form.html",
            planned=pl,
            action=f"/planned/{planned_id}",
            categories=categories_service.list_all(conn, user_id),
            accounts=accounts_service.list_all(conn, user_id),
            errors=check.errors,
            status_code=422,
        )
    assert check.op_date is not None and check.minor is not None
    planned_service.update(
        conn,
        user_id,
        planned_id,
        PatchPlannedTransaction(
            operation_date=check.op_date,
            category_id=category_id,
            account_id=account_id,
            amount=check.minor,
            description=description,
        ),
    )
    # Hosted by every page (T-D151): no row swap; refetch on the ledger, reload elsewhere.
    html = Response()
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, "/ledger")
    return html


@router.post("/{planned_id}/delete")
def delete_planned(
    planned_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    planned_service.soft_delete(conn, user_id, planned_id)
    resp = Response(content="", media_type="text/html")
    trigger(resp, Event.FORECAST_STALE, Event.LEDGER_STALE)
    return resp


@router.post("/{planned_id}/restore")
def restore_planned(
    planned_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """T-R70 — undo a soft-delete (ADR-0019)."""
    try:
        planned_service.undelete(conn, user_id, planned_id)
    except LookupError:
        return Response(status_code=404, content="not found")
    resp = Response(content="", media_type="text/html")
    trigger(resp, Event.FORECAST_STALE, Event.LEDGER_STALE)
    return resp


@router.get("/{planned_id}/promote", response_class=HTMLResponse)
def promote_form(
    planned_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return render(
            request,
            "partials/planned/_promote_modal.html",
            planned=None,
            errors={"planned": "not found"},
            status_code=404,
        )
    acc = accounts_service.find_by_id(conn, user_id, pl.account_id)
    return render(
        request,
        "partials/planned/_promote_modal.html",
        planned=pl,
        account=acc,
        errors={},
    )


@router.get("/{planned_id}/promote/inline", response_class=HTMLResponse)
def promote_inline(
    planned_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """F-02 — Row-expand inline Promote form for Today Upcoming."""
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    acc = accounts_service.find_by_id(conn, user_id, pl.account_id)
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    return render(
        request,
        "partials/planned/_promote_inline_row.html",
        planned=pl,
        account=acc,
        categories_by_id=categories_by_id,
    )


@router.post("/{planned_id}/promote")
def promote_submit(
    planned_id: int,
    request: Request,
    *,
    operation_date: str = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    acc = accounts_service.find_by_id(conn, user_id, pl.account_id)
    op_date = parse_date(operation_date)
    errors: dict[str, str] = {}
    if op_date is None:
        errors["operation_date"] = "invalid date"
    minor: int | None = None
    if acc is not None:
        minor, err = positive_amount(amount, acc.currency)
        if err:
            errors["amount"] = err
    if errors:
        return render(
            request,
            "partials/planned/_promote_modal.html",
            planned=pl,
            account=acc,
            errors=errors,
            status_code=422,
        )
    assert op_date is not None and minor is not None
    try:
        planned_service.promote_to_actual(
            conn,
            user_id,
            planned_id,
            planned_service.PromotionEdits(
                operation_date=op_date,
                amount_minor=minor,
                description=description or None,
            ),
        )
    except (
        planned_service.AlreadyPromotedError,
        planned_service.CannotPromoteDeletedError,
        planned_service.UnsupportedDirectionError,
        planned_service.ValidationError,
    ) as exc:
        return render(
            request,
            "partials/planned/_promote_modal.html",
            planned=pl,
            account=acc,
            errors={"promotion": str(exc)},
            status_code=422,
        )
    html = Response()
    trigger(html, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, "/ledger")
    return html


@router.get("/export")
def export(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> Response:
    fmt = request.query_params.get("format", "csv")
    flt = ledger_data.parse_planned_filter(request)
    views = list(planned_service.list_planned(conn, user_id, flt, today=today))
    rows = [
        {
            "key": v.persisted_id if v.persisted_id is not None else -1,
            "operation_date": v.operation_date,
            "amount_minor": v.amount_minor,
            "description": v.description,
            "kind": str(v.kind),
            "is_promoted": v.is_promoted,
        }
        for v in views
    ]
    columns = [
        export_service.ExportColumn(key="key", header="id", kind="int"),
        export_service.ExportColumn(key="operation_date", header="date", kind="date"),
        export_service.ExportColumn(key="amount_minor", header="amount_minor", kind="money_minor"),
        export_service.ExportColumn(key="description", header="description", kind="str"),
        export_service.ExportColumn(key="kind", header="kind", kind="str"),
        export_service.ExportColumn(key="is_promoted", header="promoted", kind="bool"),
    ]
    stamp = today.strftime("%Y%m%d")
    if fmt == "parquet":
        return Response(
            content=export_service.export_parquet(rows, columns),
            media_type="application/vnd.apache.parquet",
            headers={"Content-Disposition": f'attachment; filename="planned_{stamp}.parquet"'},
        )
    return Response(
        content=export_service.export_csv(rows, columns),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="planned_{stamp}.csv"'},
    )
