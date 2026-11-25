"""Planned transactions router (T-034)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Final

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.planned import (
    PatchPlannedTransaction,
)
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    export as export_service,
    planned as planned_service,
)
from budget_planner.web import entry_forms, form_responses, ledger_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.htmx import Event, refresh_unless_on, toast_payload, trigger
from budget_planner.web.http_headers import CONTENT_DISPOSITION, HTML_MEDIA_TYPE
from budget_planner.web.params import EXPORT_FORMATS, query_choice
from budget_planner.web.paths import LEDGER_PATH, NEW_PATH, TABLE_PATH
from budget_planner.web.rendering import SLIDEOVER_TEMPLATE, render

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


@router.get(TABLE_PATH, response_class=HTMLResponse)
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


@router.get(NEW_PATH, response_class=HTMLResponse)
def new_form(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """The new-entry dialog on the planned tab (T-UR07b)."""
    return form_responses.open_new_entry(request, conn, user_id, tab="planned")


@router.post("")
def create_planned(
    request: Request,
    *,
    operation_date: str = Form(""),
    category_id: str = Form(""),
    category: str = Form(""),
    account_id: str = Form(""),
    amount: str = Form(""),
    description: str = Form(""),
    dest_account_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    # The dialog posts the picker's "category" (vendored combobox.js), the old form category_id.
    chosen = entry_forms.category_choice(category_id, category)
    check = entry_forms.check_planned_create(
        conn,
        user_id,
        operation_date=operation_date,
        category_id=chosen,
        account_id=entry_forms.account_choice(account_id),
        amount=amount,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return form_responses.entry_create_errors(
            request,
            conn,
            user_id,
            tab="planned",
            chosen=chosen,
            errors=check.errors,
            posted=entry_forms.posted_entry(
                chosen,
                account_id,
                amount,
                operation_date=operation_date,
                description=description,
                dest_account_id=dest_account_id,
            ),
        )
    pl = entry_forms.save_planned(conn, user_id, check, description)
    return form_responses.created_planned_response(request, pl, check)


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
        SLIDEOVER_TEMPLATE,
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
        return form_responses.planned_form_errors(
            request, conn, user_id, planned=pl, errors=check.errors
        )
    op_date, amount_minor = check.valid_values()
    planned_service.update(
        conn,
        user_id,
        planned_id,
        PatchPlannedTransaction(
            operation_date=op_date,
            category_id=category_id,
            account_id=account_id,
            amount=amount_minor,
            description=description,
        ),
    )
    # Hosted by every page (T-D151): no row swap; refetch on the ledger, reload elsewhere.
    return form_responses.stale_refresh(request, Event.FORECAST_STALE, Event.LEDGER_STALE)


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
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
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
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.FORECAST_STALE, Event.LEDGER_STALE)
    return resp


@router.get("/{planned_id}/promote", response_class=HTMLResponse)
def promote_form(
    planned_id: int,
    request: Request,
    dialog: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="planned: not found")
    acc = accounts_service.find_by_id(conn, user_id, pl.account_id)
    return form_responses.promote_planned_dialog(
        request, conn, user_id, pl, acc, as_dialog=bool(dialog)
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
    operation_date: str = Form(""),
    amount: str = Form(""),
    description: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_service.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    acc = accounts_service.find_by_id(conn, user_id, pl.account_id)
    op_date, minor, errors = entry_forms.check_promote_input(acc, operation_date, amount)
    posted = {"amount": amount, "operation_date": operation_date, "description": description}
    if errors or op_date is None or minor is None:
        return form_responses.promote_planned_dialog(
            request, conn, user_id, pl, acc, posted=posted, errors=errors
        )
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
        return form_responses.promote_planned_dialog(
            request, conn, user_id, pl, acc, posted=posted, errors={"promotion": str(exc)}
        )
    html = Response()
    trigger(html, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, LEDGER_PATH)
    return html


@router.get("/export")
def export(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> Response:
    fmt = query_choice("format", request.query_params.get("format"), EXPORT_FORMATS) or "csv"
    flt = ledger_data.parse_planned_filter(request, today)
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
            headers={CONTENT_DISPOSITION: f'attachment; filename="planned_{stamp}.parquet"'},
        )
    return Response(
        content=export_service.export_csv(rows, columns),
        media_type="text/csv; charset=utf-8",
        headers={CONTENT_DISPOSITION: f'attachment; filename="planned_{stamp}.csv"'},
    )
