"""Shared form-failure and success responses for the entry routers (T-Q270).

Transactions, planned and accounts re-render the same form with errors (422) or
answer a saved edit with stale-events; the routers call these instead of
repeating the render blocks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.accounts import Account
from budget_planner.domain.planned import PlannedTransaction
from budget_planner.domain.transactions import Transaction
from budget_planner.services import accounts as accounts_service, categories as categories_service
from budget_planner.web import accounts_data, entry_forms, ledger_data
from budget_planner.web.deps import today_for
from budget_planner.web.dialogs import dialog_response, invalid_dialog_response
from budget_planner.web.htmx import Event, refresh_unless_on, trigger
from budget_planner.web.paths import LEDGER_PATH, PLANNED_PATH, TRANSACTIONS_PATH
from budget_planner.web.rendering import is_hx_request, render

_TXN_FORM = "partials/transactions/_form.html"
_PLANNED_FORM = "partials/planned/_form.html"
PROMOTE_TEMPLATE = "pages/entries/promote.html"
_RECONCILE_MODAL = "partials/accounts/_reconcile_modal.html"
_UNPROCESSABLE = 422
NEW_ENTRY_TEMPLATE = "pages/entries/new-entry.html"
_NEW_ENTRY_PAGE = "pages/entries/open.html"
_HX_TARGET = "HX-Target"
_MODAL_ROOT_ID = "modal-root"


def from_dialog(request: Request) -> bool:
    """True when the post came from a dialog form (it targets ``#modal-root``, ADR-0107)."""
    return request.headers.get(_HX_TARGET, "") == _MODAL_ROOT_ID


def open_new_entry(
    request: Request, conn: sqlite3.Connection, user_id: int, *, tab: str
) -> Response:
    """The new-entry dialog on ``tab``; a plain page load gets a shell page that opens it."""
    if not is_hx_request(request):
        return render(request, _NEW_ENTRY_PAGE, nav_current="", tab=tab)
    context = entry_forms.new_entry_context(
        conn,
        user_id,
        tab=tab,
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
    )
    return dialog_response(request, NEW_ENTRY_TEMPLATE, context)


def entry_create_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    tab: str,
    chosen: int,
    errors: dict[str, str],
    posted: Mapping[str, str],
) -> Response:
    """422 of a happened or planned create: the dialog it was posted from, else the old form."""
    shown = entry_forms.pick_category_error(errors, chosen)
    if from_dialog(request):
        return new_entry_errors(request, conn, user_id, tab=tab, posted=posted, errors=shown)
    if tab == "happened":
        return txn_form_errors(request, conn, user_id, txn=None, errors=shown)
    return planned_form_errors(request, conn, user_id, planned=None, errors=shown)


def new_entry_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    tab: str,
    posted: Mapping[str, str],
    errors: Mapping[str, str],
    terms: Sequence[Mapping[str, object]] | None = None,
) -> Response:
    """422: the new-entry dialog again with the posted values, the summary and field errors."""
    context = entry_forms.new_entry_context(
        conn,
        user_id,
        tab=tab,
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
        posted=posted,
        terms=terms,
    )
    return invalid_dialog_response(request, NEW_ENTRY_TEMPLATE, context, errors)


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


def promote_planned_dialog(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    planned: PlannedTransaction,
    account: Account | None,
    *,
    posted: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
) -> Response:
    """The promote dialog for a planned item: prefill (200) or posted values with errors (422)."""
    context = entry_forms.promote_context(
        conn,
        user_id,
        action=f"{PLANNED_PATH}/{planned.id}/promote",
        category_id=planned.category_id,
        account=account,
        amount_minor=planned.amount,
        date_value=planned.operation_date,
        note_value=planned.description,
        base_currency=request.app.state.settings.base_currency,
        posted=posted,
    )
    if errors:
        return invalid_dialog_response(request, PROMOTE_TEMPLATE, context, errors)
    return dialog_response(request, PROMOTE_TEMPLATE, context)


def reconcile_modal_error(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    acc: Account,
    derived: int,
    message: str,
) -> Response:
    return render(
        request,
        _RECONCILE_MODAL,
        errors={"actual_balance": message},
        status_code=_UNPROCESSABLE,
        **accounts_data.reconcile_modal_context(conn, user_id, acc, derived),
    )


def stale_refresh(request: Request, *events: Event) -> Response:
    """Empty answer for a form hosted on every page: ledger refetches, others reload."""
    html = Response()
    trigger(html, *events)
    refresh_unless_on(request, html, LEDGER_PATH)
    return html


def created_txn_response(
    request: Request, conn: sqlite3.Connection, user_id: int, new_txn: Transaction
) -> Response:
    """A saved transaction: its row, the stale events, a reload off the ledger."""
    row = ledger_data.hydrate_txn_rows(conn, user_id, [new_txn])[0]
    html = render(request, "partials/transactions/_row.html", txn=row)
    trigger(html, Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, LEDGER_PATH)
    return html


def created_planned_response(
    request: Request, planned: PlannedTransaction, check: entry_forms.EntryCheck
) -> Response:
    """A saved planned item: its row, the stale events, a reload off the ledger (T-D142)."""
    view = ledger_data.planned_row_from_persisted(planned, check.account, check.category)
    html = render(request, "partials/planned/_row.html", view=view)
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, LEDGER_PATH)
    return html
