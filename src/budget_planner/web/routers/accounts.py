"""Accounts router (T-032).

Lists accounts with derived balance + stats, create/rename/soft-delete,
snapshot capture, and reconciliation. Business logic in services; this
router parses + renders.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
)
from budget_planner.web import accounts_data, form_responses
from budget_planner.web.account_forms import (
    parse_account_patch,
    parse_new_account,
    parse_save_snapshot,
)
from budget_planner.web.accounts_view import (
    account_dialog,
    delete_dialog,
    snapshot_line,
)
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.dialogs import dialog_response, invalid_dialog_response, saved_response
from budget_planner.web.htmx import Event, toast_payload, trigger
from budget_planner.web.http_headers import HTML_MEDIA_TYPE, HX_REFRESH, HX_RESWAP
from budget_planner.web.paths import NEW_PATH
from budget_planner.web.rendering import render, render_context

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    data: dict[str, Any] = accounts_data.hydrate(conn, user_id, settings)
    return render(request, "pages/accounts/index.html", nav_current="accounts", **data)


_ACCOUNT_DIALOG = "pages/accounts/dialog-account.html"
_DELETE_DIALOG = "pages/accounts/dialog-delete.html"
_RECONCILE_DIALOG = "pages/accounts/dialog-reconcile.html"
_ROW = "fragments/rows/account-row.html"
_NOT_FOUND = "account not found"


@router.get(NEW_PATH, response_class=HTMLResponse)
def new_form(request: Request, settings: Settings = Depends(get_settings_dep)) -> HTMLResponse:
    dlg = account_dialog(None, base_currency=settings.base_currency)
    return dialog_response(request, _ACCOUNT_DIALOG, {"dlg": dlg, "errors": {}})


@router.post("")
def create_account(
    request: Request,
    *,
    name: str = Form(""),
    currency: str = Form(""),
    opening_balance: str = Form("0"),
    type: str = Form(""),
    is_liability: str = Form(""),
    credit_limit: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    parsed = parse_new_account(
        name=name,
        currency=currency,
        opening_balance=opening_balance,
        account_type=type,
        is_liability=is_liability,
        credit_limit=credit_limit,
    )
    if parsed.command is None:
        values = {
            "name": name,
            "currency": currency,
            "opening_balance": opening_balance,
            "type": type,
            "is_liability": is_liability,
            "credit_limit": credit_limit,
        }
        dlg = account_dialog(
            None, values=values, base_currency=settings.base_currency, errors=parsed.errors
        )
        return invalid_dialog_response(request, _ACCOUNT_DIALOG, {"dlg": dlg}, parsed.errors)
    acc = accounts_service.create(conn, user_id, parsed.command)
    html = render_context(request, _ROW, accounts_data.row_context(conn, user_id, acc.id, settings))
    trigger(html, Event.BALANCE_STALE)
    # T-D150: the accounts list has no region that refetches on a trigger for a new row,
    # so skip the swap and reload to show the new item (the reload also closes the dialog).
    html.headers[HX_RESWAP] = "none"
    html.headers[HX_REFRESH] = "true"
    return html


@router.get("/{account_id}/edit", response_class=HTMLResponse)
def edit_form(
    account_id: int,
    request: Request,
    *,
    intent: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """The edit dialog; ``?intent=delete`` opens the delete confirm (or its blocked variant)."""
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content=_NOT_FOUND)
    refs = accounts_service.account_references(conn, user_id, account_id)
    if intent == "delete":
        balance = balance_service.derive_balance(conn, user_id, account_id)
        ctx: dict[str, object] = {"dlg": delete_dialog(acc, refs, balance)}
        return dialog_response(request, _DELETE_DIALOG, ctx)
    dlg = account_dialog(acc, base_currency=settings.base_currency, txn_count=refs.transactions)
    return dialog_response(request, _ACCOUNT_DIALOG, {"dlg": dlg, "errors": {}})


@router.post("/{account_id}")
def update_account(
    account_id: int,
    request: Request,
    *,
    name: str = Form(""),
    type: str = Form(""),
    is_liability: str = Form(""),
    credit_limit: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content=_NOT_FOUND)
    parsed = parse_account_patch(
        acc, name=name, account_type=type, is_liability=is_liability, credit_limit=credit_limit
    )
    if parsed.patch is None:
        values = {
            "name": name,
            "type": type,
            "is_liability": is_liability,
            "credit_limit": credit_limit,
        }
        dlg = account_dialog(
            acc, values=values, base_currency=settings.base_currency, errors=parsed.errors
        )
        return invalid_dialog_response(request, _ACCOUNT_DIALOG, {"dlg": dlg}, parsed.errors)
    accounts_service.update(conn, user_id, account_id, parsed.patch)
    return saved_response(
        request,
        _ROW,
        accounts_data.row_context(conn, user_id, account_id, settings),
        message=f"{name.strip()} saved",
        events=(Event.BALANCE_STALE,),
    )


@router.post("/{account_id}/delete")
def delete_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    # The delete dialog swaps this empty body into #modal-root (closing it); the accounts
    # panel refetches on balance-stale, which drops the row. Unknown, foreign and already
    # archived ids are one 404 with no toast (operator decision Q15, T-UR08c).
    if accounts_service.find_by_id(conn, user_id, account_id) is None:
        return Response(status_code=404, content=_NOT_FOUND)
    accounts_service.archive_account(conn, user_id, account_id)
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
    trigger(
        resp,
        Event.BALANCE_STALE,
        Event.FORECAST_STALE,
        toast=toast_payload("success", "Account deleted"),
    )
    return resp


@router.post("/{account_id}/snapshot")
def take_snapshot(
    account_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content="not found")
    bal = balance_service.derive_balance(conn, user_id, account_id)
    snap = accounts_service.create_snapshot(
        conn, user_id, NewAccountSnapshot(account_id=account_id, balance=bal, note="user snapshot")
    )
    resp = render(
        request,
        "fragments/rows/reconcile-snapshot.html",
        snapshot=snapshot_line(snap),
        currency=acc.currency,
    )
    trigger(resp, toast=toast_payload("success", "Snapshot saved"))
    return resp


@router.get("/{account_id}/reconcile", response_class=HTMLResponse)
def reconcile_form(
    account_id: int,
    request: Request,
    actual_balance: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content=_NOT_FOUND)
    return form_responses.reconcile_dialog_response(
        request, conn, user_id, acc, actual_text=actual_balance
    )


@router.post("/{account_id}/reconcile")
def reconcile_submit(
    account_id: int,
    request: Request,
    *,
    actual_balance: str = Form(""),
    category_id: str = Form(""),
    save_snapshot: str = Form(""),
    preview: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Book the reconcile adjustment; ``?preview=1`` only re-renders the dialog's difference."""
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content="not found")
    typed: dict[str, Any] = {
        "actual_text": actual_balance,
        "category_id": category_id,
        "save_snapshot": parse_save_snapshot(save_snapshot),
    }
    if preview:
        return form_responses.reconcile_dialog_response(request, conn, user_id, acc, **typed)
    refused = accounts_data.book_reconcile(conn, user_id, acc, settings, **typed)
    if refused is not None:
        return form_responses.reconcile_modal_error(
            request, conn, user_id, acc=acc, message=refused, **typed
        )
    return saved_response(
        request,
        _ROW,
        accounts_data.row_context(conn, user_id, account_id, settings),
        message=f"{acc.name} reconciled",
        events=(Event.BALANCE_STALE, Event.FORECAST_STALE),
    )
