"""Transactions router (T-031).

Thin HTTP surface over `services.transactions` + `services.export`.
Parses form input, calls the service / repo, renders Jinja fragments.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.transactions import NewTransaction, PatchTransaction
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    export as export_service,
    transactions as transactions_service,
)
from budget_planner.services.limit_preview import compute_limit_preview
from budget_planner.web import entry_forms, form_responses, ledger_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.htmx import Event, refresh_unless_on, trigger
from budget_planner.web.http_headers import CONTENT_DISPOSITION, HTML_MEDIA_TYPE
from budget_planner.web.params import EXPORT_FORMATS, query_choice, query_int
from budget_planner.web.paths import LEDGER_PATH, NEW_PATH, TABLE_PATH
from budget_planner.web.rendering import SLIDEOVER_TEMPLATE, render

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def list_page() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the unified ledger with the ``actual`` view selected. Kept at
    ``302`` for one release per ADR-0023; a follow-up task flips to ``301``.
    The HTMX fragment alias ``/transactions/table`` and the CRUD sub-routes
    (``/transactions/new``, ``/transactions/{id}/edit``, etc.) remain live.
    """
    return RedirectResponse(url="/ledger?view=actual", status_code=302)


@router.get("/_limit_preview", response_class=HTMLResponse)
def limit_preview(
    request: Request,
    *,
    account_id: str = "",
    category_id: str = "",
    amount: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    acc_id = query_int("account_id", account_id)
    cat_id = query_int("category_id", category_id)
    preview = None
    if acc_id is not None and cat_id is not None:
        preview = compute_limit_preview(
            conn, user_id, account_id=acc_id, category_id=cat_id, amount_raw=amount
        )
    return render(request, "partials/transactions/_limit_preview.html", preview=preview)


@router.get(TABLE_PATH, response_class=HTMLResponse)
def table_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    """Legacy fragment alias (T-064).

    Delegates to the unified ledger fragment with ``view=actual`` so pre-T-064
    HTMX scripts keep working. The response shape (``#txn-table`` container,
    row ids ``#txn-{id}``) is preserved by the ledger template.
    """
    return ledger_data.render_table_for(
        request, conn, user_id, settings=settings, view="actual", today=today
    )


@router.get(NEW_PATH, response_class=HTMLResponse)
def new_form(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    # T-069 — wrap the form in a slide-over so the FAB can swap it into
    # `#modal-root`. The inner include preserves the legacy fragment shape
    # (same form fields + hx-post target) so existing tests + flows stand.
    return render(
        request,
        SLIDEOVER_TEMPLATE,
        slide_over_title="New transaction",
        form_include="partials/transactions/_form.html",
        action="/transactions",
        method="post",
        txn=None,
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors={},
    )


@router.post("")
def create_txn(
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
    check = entry_forms.check_txn_create(
        conn,
        user_id,
        operation_date=operation_date,
        category_id=category_id,
        account_id=account_id,
        amount=amount,
        description=description,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return form_responses.txn_form_errors(request, conn, user_id, txn=None, errors=check.errors)
    assert check.op_date is not None and check.minor is not None
    new_txn = transactions_service.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=check.op_date,
            category_id=category_id,
            account_id=account_id,
            amount=check.minor,
            description=description,
            dest_account_id=check.dest_id,
        ),
    )
    row = ledger_data.hydrate_txn_rows(conn, user_id, [new_txn])[0]
    html = render(request, "partials/transactions/_row.html", txn=row)
    trigger(html, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE)
    # The form is hosted by every page's Add overlay, not just the ledger: no
    # row insert; the ledger refetches on `ledger-stale`, other pages reload.
    refresh_unless_on(request, html, LEDGER_PATH)
    return html


@router.get("/{txn_id}/edit", response_class=HTMLResponse)
def edit_form(
    txn_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    txn = transactions_service.find_by_id(conn, user_id, txn_id)
    if txn is None:
        return render(
            request,
            "partials/transactions/_form.html",
            action="",
            method="post",
            txn=None,
            categories=[],
            accounts=[],
            errors={"txn": "not found"},
            status_code=404,
        )
    # T-114 / ADR-0030 §4 — wrap edit in slide-over so clicking Edit opens a
    # dialog rather than replacing the ledger row inline (which broke tbody
    # structure and visually removed the row).
    return render(
        request,
        SLIDEOVER_TEMPLATE,
        slide_over_title="Edit transaction",
        form_include="partials/transactions/_form.html",
        action=f"/transactions/{txn_id}",
        method="post",
        txn=txn,
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors={},
    )


@router.post("/{txn_id}")
def update_txn(
    txn_id: int,
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
    existing = transactions_service.find_by_id(conn, user_id, txn_id)
    if existing is None:
        return form_responses.txn_not_found(request)
    check = entry_forms.check_txn_update(
        conn,
        user_id,
        existing_dest_id=existing.dest_account_id,
        operation_date=operation_date,
        category_id=category_id,
        account_id=account_id,
        amount=amount,
        description=description,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return form_responses.txn_form_errors(
            request, conn, user_id, txn=existing, errors=check.errors
        )
    assert check.op_date is not None and check.minor is not None
    transactions_service.update(
        conn,
        user_id,
        txn_id,
        PatchTransaction(
            operation_date=check.op_date,
            category_id=category_id,
            account_id=account_id,
            amount=check.minor,
            description=description,
            dest_account_id=check.dest_id,
        ),
    )
    # The edit form is hosted by every page (T-D151): no row swap; the ledger
    # refetches on `ledger-stale`, other pages reload.
    return form_responses.stale_refresh(
        request, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE
    )


@router.post("/{txn_id}/delete")
def delete_txn(
    txn_id: int, conn: sqlite3.Connection = Depends(get_db), user_id: int = Depends(current_user_id)
) -> Response:
    transactions_service.soft_delete(conn, user_id, txn_id)
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE)
    return resp


@router.post("/{txn_id}/restore")
def restore_txn(
    txn_id: int, conn: sqlite3.Connection = Depends(get_db), user_id: int = Depends(current_user_id)
) -> Response:
    """T-R70 — undo a soft-delete (ADR-0019)."""
    try:
        transactions_service.undelete(conn, user_id, txn_id)
    except LookupError:
        return Response(status_code=404, content="not found")
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE)
    return resp


@router.get("/export")
def export(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> Response:
    fmt = query_choice("format", request.query_params.get("format"), EXPORT_FORMATS) or "csv"
    flt = ledger_data.parse_txn_filter(request)
    rows = transactions_service.list_filtered(conn, user_id, flt)
    hydrated = ledger_data.hydrate_txn_rows(conn, user_id, rows)
    export_rows = [
        {
            "id": r.id,
            "operation_date": r.operation_date,
            "amount_minor": r.amount,
            "currency": r.currency,
            "description": r.description or "",
            "category": r.category.name if r.category else "",
            "account": r.account.name if r.account else "",
            "dest_account": r.dest_account.name if r.dest_account else "",
        }
        for r in hydrated
    ]
    columns = [
        export_service.ExportColumn(key="id", header="id", kind="int"),
        export_service.ExportColumn(key="operation_date", header="date", kind="date"),
        export_service.ExportColumn(key="amount_minor", header="amount_minor", kind="money_minor"),
        export_service.ExportColumn(key="currency", header="currency", kind="str"),
        export_service.ExportColumn(key="description", header="description", kind="str"),
        export_service.ExportColumn(key="category", header="category", kind="str"),
        export_service.ExportColumn(key="account", header="account", kind="str"),
        export_service.ExportColumn(key="dest_account", header="dest_account", kind="str"),
    ]
    stamp = today.strftime("%Y%m%d")
    if fmt == "parquet":
        body = export_service.export_parquet(export_rows, columns)
        return Response(
            content=body,
            media_type="application/vnd.apache.parquet",
            headers={CONTENT_DISPOSITION: f'attachment; filename="transactions_{stamp}.parquet"'},
        )
    body = export_service.export_csv(export_rows, columns)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={CONTENT_DISPOSITION: f'attachment; filename="transactions_{stamp}.csv"'},
    )
