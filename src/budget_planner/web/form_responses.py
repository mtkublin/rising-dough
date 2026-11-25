"""Shared form-failure and success responses for the entry routers (T-Q270).

Transactions, planned and accounts re-render the same form with errors (422) or
answer a saved edit with stale-events; the routers call these instead of
repeating the render blocks.
"""

from __future__ import annotations

import sqlite3

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.accounts import Account
from budget_planner.domain.planned import PlannedTransaction
from budget_planner.domain.transactions import Transaction
from budget_planner.services import accounts as accounts_service, categories as categories_service
from budget_planner.web import accounts_data
from budget_planner.web.dialogs import dialog_response, invalid_dialog_response
from budget_planner.web.htmx import Event, refresh_unless_on, trigger
from budget_planner.web.paths import LEDGER_PATH, PLANNED_PATH, TRANSACTIONS_PATH
from budget_planner.web.rendering import render

_TXN_FORM = "partials/transactions/_form.html"
_PLANNED_FORM = "partials/planned/_form.html"
_PROMOTE_MODAL = "partials/planned/_promote_modal.html"
_RECONCILE_DIALOG = "pages/accounts/dialog-reconcile.html"
_UNPROCESSABLE = 422


def txn_not_found(request: Request) -> Response:
    return render(
        request,
        _TXN_FORM,
        action="",
        method="post",
        txn=None,
        categories=[],
        accounts=[],
        errors={"txn": "not found"},
        status_code=404,
    )


def txn_form_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    txn: Transaction | None,
    errors: dict[str, str],
) -> Response:
    """Re-render the form; a ``None`` txn is the create form."""
    return render(
        request,
        _TXN_FORM,
        action=f"{TRANSACTIONS_PATH}/{txn.id}" if txn else TRANSACTIONS_PATH,
        method="post",
        txn=txn,
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors=errors,
        status_code=_UNPROCESSABLE,
    )


def planned_form_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    planned: PlannedTransaction | None,
    errors: dict[str, str],
) -> Response:
    """Re-render the form; a ``None`` planned is the create form."""
    return render(
        request,
        _PLANNED_FORM,
        planned=planned,
        action=f"{PLANNED_PATH}/{planned.id}" if planned else PLANNED_PATH,
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors=errors,
        status_code=_UNPROCESSABLE,
    )


def promote_modal_errors(
    request: Request,
    planned: PlannedTransaction,
    account: Account | None,
    errors: dict[str, str],
) -> Response:
    return render(
        request,
        _PROMOTE_MODAL,
        planned=planned,
        account=account,
        errors=errors,
        status_code=_UNPROCESSABLE,
    )


def reconcile_modal_error(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    acc: Account,
    message: str,
    actual_text: str = "",
    category_id: str = "",
    save_snapshot: bool = False,
) -> Response:
    """The reconcile dialog again with the rejected amount (422, ADR-0143)."""
    ctx, _ = accounts_data.reconcile_dialog_context(
        conn,
        user_id,
        acc,
        actual_text=actual_text,
        category_id=category_id,
        save_snapshot=save_snapshot,
        message=message,
    )
    return invalid_dialog_response(request, _RECONCILE_DIALOG, ctx, {"actual_balance": message})


def reconcile_dialog_response(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    acc: Account,
    *,
    actual_text: str = "",
    category_id: str = "",
    save_snapshot: bool = False,
) -> Response:
    """The reconcile dialog for an optional typed amount: 200, or 422 when the amount is bad."""
    ctx, errors = accounts_data.reconcile_dialog_context(
        conn,
        user_id,
        acc,
        actual_text=actual_text,
        category_id=category_id,
        save_snapshot=save_snapshot,
    )
    if errors:
        return invalid_dialog_response(request, _RECONCILE_DIALOG, ctx, errors)
    return dialog_response(request, _RECONCILE_DIALOG, {**ctx, "errors": {}})


def stale_refresh(request: Request, *events: Event) -> Response:
    """Empty answer for a form hosted on every page: ledger refetches, others reload."""
    html = Response()
    trigger(html, *events)
    refresh_unless_on(request, html, LEDGER_PATH)
    return html
