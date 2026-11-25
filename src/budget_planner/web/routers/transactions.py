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
from budget_planner.services import (
    export as export_service,
    transactions as transactions_service,
)
from budget_planner.services.limit_preview import compute_limit_preview
from budget_planner.web import entry_forms, form_responses, ledger_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.htmx import Event, toast_payload, trigger
from budget_planner.web.http_headers import CONTENT_DISPOSITION, HTML_MEDIA_TYPE
from budget_planner.web.params import EXPORT_FORMATS, query_choice, query_int
from budget_planner.web.paths import TABLE_PATH
from budget_planner.web.rendering import render

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
def list_page() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the unified ledger with the ``actual`` view selected. Kept at
    ``302`` for one release per ADR-0023; a follow-up task flips to ``301``.
    The HTMX fragment alias ``/transactions/table`` and the CRUD sub-routes
    (``/transactions/{id}/edit``, etc.) remain live; the new-entry dialog is ``/add``.
    """
    return RedirectResponse(url="/ledger?view=actual", status_code=302)


@router.get("/_limit_preview", response_class=HTMLResponse)
def limit_preview(
    request: Request,
    *,
    account_id: str = "",
    category_id: str = "",
    category: str = "",
    amount: str = "",
    txn_id: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    edited_id = query_int("txn_id", txn_id)
    acc_id = query_int("account_id", account_id)
    cat_id = query_int("category_id", category_id)
    cat_id = cat_id if cat_id is not None else query_int("category", category)
    preview = None
    if acc_id is not None and cat_id is not None:
        preview = compute_limit_preview(
            conn,
            user_id,
            account_id=acc_id,
            category_id=cat_id,
            amount_raw=amount,
            exclude_txn_id=edited_id,
        )
    # The dialog line refetches itself (HX-Target credit-line); the old form keeps its partial.
    if request.headers.get("HX-Target") == "credit-line":
        return render(request, "fragments/fields/credit-line.html", preview=preview)
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


@router.post("")
def create_txn(
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
    check = entry_forms.check_txn_create(
        conn,
        user_id,
        operation_date=operation_date,
        category_id=chosen,
        account_id=entry_forms.account_choice(account_id),
        amount=amount,
        description=description,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return form_responses.entry_create_errors(
            request,
            conn,
            user_id,
            tab="happened",
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
    entry_forms.save_txn(conn, user_id, check, description)
    return form_responses.created_txn_response(request)


@router.get("/{txn_id}/edit", response_class=HTMLResponse)
def edit_form(
    txn_id: int,
    request: Request,
    hero: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """The edit dialog (T-UR09b); ``hero=1`` re-renders it for the hero refresh."""
    txn = transactions_service.find_by_id(conn, user_id, txn_id)
    if txn is None:
        return form_responses.txn_not_found()
    if hero:
        return form_responses.edit_transaction_hero(request, conn, user_id, txn)
    return form_responses.open_edit_transaction(request, conn, user_id, txn)


@router.post("/{txn_id}")
def update_txn(
    txn_id: int,
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
    existing = transactions_service.find_by_id(conn, user_id, txn_id)
    if existing is None:
        return form_responses.txn_not_found()
    # The dialog posts the picker's "category" (vendored combobox.js); a missing field is a 422.
    chosen = entry_forms.category_choice(category_id, category)
    account = entry_forms.account_choice(account_id)
    check = entry_forms.check_txn_update(
        conn,
        user_id,
        existing_dest_id=existing.dest_account_id,
        operation_date=operation_date,
        category_id=chosen,
        account_id=account,
        amount=amount,
        description=description,
        dest_account_id=dest_account_id,
    )
    if check.errors:
        return form_responses.edit_transaction_errors(
            request,
            conn,
            user_id,
            existing,
            posted=entry_forms.posted_entry(
                chosen,
                account_id,
                amount,
                operation_date=operation_date,
                description=description,
                dest_account_id=dest_account_id,
            ),
            errors=entry_forms.pick_category_error(check.errors, chosen),
        )
    entry_forms.save_txn_update(conn, user_id, txn_id, check, description)
    return form_responses.updated_txn_response(request)


@router.post("/{txn_id}/delete")
def delete_txn(
    txn_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    transactions_service.soft_delete(conn, user_id, txn_id)
    return form_responses.deleted_txn_response(request, txn_id)


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
    trigger(
        resp,
        Event.BALANCE_STALE,
        Event.FORECAST_STALE,
        Event.LEDGER_STALE,
        toast=toast_payload("success", "Transaction restored"),
    )
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
