"""Shared form-failure and success responses for the entry routers (T-Q270).

Transactions, planned and accounts re-render the same form with errors (422) or
answer a saved edit with stale-events; the routers call these instead of
repeating the render blocks.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from types import MappingProxyType

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.accounts import Account
from budget_planner.domain.money import format_major
from budget_planner.domain.planned import PlannedTransaction
from budget_planner.domain.transactions import Transaction
from budget_planner.services import accounts as accounts_service, categories as categories_service
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web import accounts_data, entry_forms, ledger_data
from budget_planner.web.deps import today_for
from budget_planner.web.dialogs import (
    dialog_response,
    invalid_dialog_response,
    removed_response,
    saved_response,
)
from budget_planner.web.htmx import Event, refresh_unless_on, trigger
from budget_planner.web.http_headers import HX_RESWAP
from budget_planner.web.params import parse_int
from budget_planner.web.paths import LEDGER_PATH, PLANNED_PATH, TRANSACTIONS_PATH
from budget_planner.web.recurring_forms import EMPTY_TERM_INPUT, formula_source_candidates
from budget_planner.web.rendering import is_hx_request, render, render_context

_TXN_FORM = "partials/transactions/_form.html"
_PLANNED_FORM = "partials/planned/_form.html"
PROMOTE_TEMPLATE = "pages/entries/promote.html"
_LEGACY_PROMOTE = "partials/planned/_promote_modal.html"
EDIT_PLANNED_TEMPLATE = "fragments/dialogs/edit-planned.html"
_RECONCILE_MODAL = "partials/accounts/_reconcile_modal.html"
_UNPROCESSABLE = 422
_NOT_FOUND = 404
EDIT_TXN_TEMPLATE = "fragments/dialogs/edit-transaction.html"
_EDIT_PAGE = "pages/entries/open-edit.html"
NEW_ENTRY_TEMPLATE = "pages/entries/new-entry.html"
_NEW_ENTRY_PAGE = "pages/entries/open.html"
_HX_TARGET = "HX-Target"
_MODAL_ROOT_ID = "modal-root"


def from_dialog(request: Request) -> bool:
    """True when the post came from a dialog form (it targets ``#modal-root``, ADR-0107)."""
    return request.headers.get(_HX_TARGET, "") == _MODAL_ROOT_ID


_LEGACY_OVERLAY = "partials/_add_entry_overlay.html"
_LEGACY_TABS = MappingProxyType(
    {
        "happened": ("partials/transactions/_form.html", "txn"),
        "planned": ("partials/planned/_form.html", "planned"),
        "repeats": ("partials/recurring/_form.html", "rule"),
    }
)


def open_legacy_overlay(
    request: Request, conn: sqlite3.Connection, user_id: int, *, tab: str
) -> Response:
    """The old shell's "+ Add" slide-over (ledger, forecast, settings) until T-UR09 / T-UR10."""
    form_include, entity = _LEGACY_TABS[tab]
    context: dict[str, object] = {
        "active_tab": tab,
        "form_include": form_include,
        "action": entry_forms.TAB_ACTIONS[tab],
        "categories": categories_service.list_all(conn, user_id),
        "accounts": accounts_service.list_all(conn, user_id),
        "errors": {},
        entity: None,
    }
    if tab == "repeats":
        context["source_categories"] = formula_source_candidates(conn, user_id)
        context["amount_source"] = "fixed"
        context["terms"] = [dict(EMPTY_TERM_INPUT)]
    return render_context(request, _LEGACY_OVERLAY, context)


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
        return txn_form_errors(request, conn, user_id, errors=shown)
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
        errors=errors,
    )
    return invalid_dialog_response(request, NEW_ENTRY_TEMPLATE, context, errors)


def new_entry_hero(
    request: Request, conn: sqlite3.Connection, user_id: int, *, tab: str, fx: FormulaFx
) -> Response:
    """The dialog rendered from the form's current values; the page swaps only its hero.

    The hero follows the chosen account (currency) and category (sign); in formula mode it shows
    the service's next amount. No retarget: the dialog's own refresh picks ``.rd-dialog__hero``.
    """
    values = dict(request.query_params)
    today = today_for(request)
    base = request.app.state.settings.base_currency
    context = entry_forms.new_entry_context(
        conn, user_id, tab=tab, today=today, base_currency=base, posted=values
    )
    if tab == "repeats" and values.get("amount_source") == "formula":
        formula = entry_forms.formula_hero(
            conn,
            user_id,
            request.query_params,
            currency=str(context["currency"]),
            today=today,
            fx=fx,
        )
        context = entry_forms.new_entry_context(
            conn, user_id, tab=tab, today=today, base_currency=base, posted=values, formula=formula
        )
    return render_context(request, NEW_ENTRY_TEMPLATE, context)


def txn_not_found() -> Response:
    """An unknown or foreign transaction id: a plain 404 (the htmx error flash reads it)."""
    return Response(status_code=_NOT_FOUND, content="not found")


def txn_form_errors(
    request: Request, conn: sqlite3.Connection, user_id: int, *, errors: dict[str, str]
) -> Response:
    """Re-render the old create form (the old shell's "+ Add" slide-over) with errors."""
    return render(
        request,
        _TXN_FORM,
        action=TRANSACTIONS_PATH,
        method="post",
        txn=None,
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        errors=errors,
        status_code=_UNPROCESSABLE,
    )


def open_edit_transaction(
    request: Request, conn: sqlite3.Connection, user_id: int, txn: Transaction
) -> Response:
    """The edit dialog of ``txn``; a plain page load gets a shell page that opens it."""
    if not is_hx_request(request):
        return render(request, _EDIT_PAGE, nav_current="", txn_id=txn.id)
    context = entry_forms.edit_context(
        conn,
        user_id,
        txn,
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
    )
    return dialog_response(request, EDIT_TXN_TEMPLATE, context)


def edit_transaction_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    txn: Transaction,
    *,
    posted: Mapping[str, str],
    errors: Mapping[str, str],
) -> Response:
    """422: the edit dialog again with the posted values, the summary and field errors."""
    context = entry_forms.edit_context(
        conn,
        user_id,
        txn,
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
        posted=posted,
        errors=errors,
    )
    return invalid_dialog_response(request, EDIT_TXN_TEMPLATE, context, errors)


def edit_transaction_hero(
    request: Request, conn: sqlite3.Connection, user_id: int, txn: Transaction
) -> Response:
    """The edit dialog rendered from the form's current values; the page swaps only its hero."""
    context = entry_forms.edit_context(
        conn,
        user_id,
        txn,
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
        posted=dict(request.query_params),
    )
    return render_context(request, EDIT_TXN_TEMPLATE, context)


def updated_txn_response(request: Request) -> Response:
    """A saved edit: close the dialog and flash it; the stale events refetch the page."""
    html = saved_response(
        request,
        None,
        {},
        message="transaction saved",
        events=(Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE),
    )
    html.headers[HX_RESWAP] = "none"
    return html


def deleted_txn_response(request: Request, txn_id: int) -> Response:
    """A deleted transaction: its row goes, the toast offers undo (restore keeps its route)."""
    return removed_response(
        request,
        message="transaction deleted",
        undo_url=f"{TRANSACTIONS_PATH}/{txn_id}/restore",
        events=(Event.BALANCE_STALE, Event.FORECAST_STALE, Event.LEDGER_STALE),
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


def _planned_values(planned: PlannedTransaction, account: Account | None) -> dict[str, str]:
    """The stored planned item as the dialog's posted text (amount in its account currency)."""
    return {
        "category": str(planned.category_id),
        "account_id": str(planned.account_id),
        "amount": format_major(planned.amount, account.currency) if account else "",
        "operation_date": planned.operation_date.isoformat(),
        "description": planned.description,
        "dest_account_id": str(planned.dest_account_id or ""),
    }


def edit_planned_context(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    planned: PlannedTransaction,
    *,
    posted: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """What ``fragments/dialogs/edit-planned.html`` renders: the stored item or the posted text."""
    account = accounts_service.find_by_id(conn, user_id, planned.account_id, include_deleted=True)
    values = dict(posted) if posted is not None else _planned_values(planned, account)
    category = categories_service.find_by_id(
        conn, user_id, planned.category_id, include_deleted=True
    )
    context = entry_forms.new_entry_context(
        conn,
        user_id,
        tab="planned",
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
        posted=values,
        errors=errors,
    )
    return {
        **context,
        "title": f"edit planned \N{MIDDLE DOT} {category.name if category else ''}",
        "action": f"{PLANNED_PATH}/{planned.id}",
        "hero_url": f"{PLANNED_PATH}/{planned.id}/edit?hero=1",
        "selected_dest_id": parse_int(values.get("dest_account_id", "")),
    }


def edit_planned_dialog(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    planned: PlannedTransaction,
    *,
    posted: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
    hero_only: bool = False,
) -> Response:
    """The edit-planned dialog: stored values (200), posted values with errors (422), or its hero.

    ``hero_only`` renders the dialog from the form's current values for the hero refresh (account
    currency, category sign); the page swaps only ``.rd-dialog__hero`` and it is not a dialog open.
    """
    context = edit_planned_context(request, conn, user_id, planned, posted=posted, errors=errors)
    if hero_only:
        return render_context(request, EDIT_PLANNED_TEMPLATE, context)
    if errors:
        return invalid_dialog_response(request, EDIT_PLANNED_TEMPLATE, context, errors)
    return dialog_response(request, EDIT_PLANNED_TEMPLATE, context)


def planned_saved(request: Request) -> Response:
    """A saved planned edit: the dialog empties, the lists refetch on the stale events."""
    return saved_response(
        request,
        None,
        {},
        message="Planned entry saved",
        events=(Event.FORECAST_STALE, Event.LEDGER_STALE),
    )


def promote_planned_dialog(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    planned: PlannedTransaction,
    account: Account | None,
    *,
    as_dialog: bool | None = None,
    posted: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
) -> Response:
    """The promote dialog for a planned item: prefill (200) or posted values with errors (422).

    ``as_dialog`` ``None`` follows the post (``from_dialog``). The old shell (ledger) still gets
    its slide-over until T-UR09 / T-UR10 (``as_dialog`` false).
    """
    if not (from_dialog(request) if as_dialog is None else as_dialog):
        return render(
            request,
            _LEGACY_PROMOTE,
            planned=planned,
            account=account,
            errors=dict(errors or {}),
            status_code=_UNPROCESSABLE if errors else 200,
        )
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
