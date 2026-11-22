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

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain.money import parse_amount_minor
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.services import (
    account_reconcile as reconcile_service,
    accounts as accounts_service,
    balance as balance_service,
    reconciliation as reconciliation_service,
)
from budget_planner.web import accounts_data
from budget_planner.web.account_forms import (
    parse_account_patch,
    parse_category_id,
    parse_new_account,
    parse_save_snapshot,
)
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.htmx import Event, toast_payload, trigger
from budget_planner.web.rendering import render

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    data: dict[str, Any] = accounts_data.hydrate(conn, user_id, settings)
    return render(request, "accounts/index.html", **data)


@router.get("/new", response_class=HTMLResponse)
def new_form(request: Request) -> HTMLResponse:
    # ADR-0030 §4 — wrap in shared slide-over so the New-account form inherits
    # the visible close affordance + Esc/backdrop dismissal.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="New account",
        form_include="partials/accounts/_form.html",
        account=None,
        action="/accounts",
        errors={},
    )


@router.post("")
def create_account(
    request: Request,
    *,
    name: str = Form(...),
    currency: str = Form(...),
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
        return render(
            request,
            "partials/accounts/_form.html",
            account=None,
            action="/accounts",
            errors=parsed.errors,
            status_code=422,
        )
    acc = accounts_service.create(conn, user_id, parsed.command)
    html = render(
        request,
        "partials/accounts/_card.html",
        card=accounts_data.single_card(conn, user_id, acc.id, settings),
    )
    trigger(html, Event.BALANCE_STALE)
    # T-D150: the form targets itself and the accounts list has no region that
    # refetches on a trigger, so skip the swap and reload to show the new item.
    html.headers["HX-Reswap"] = "none"
    html.headers["HX-Refresh"] = "true"
    return html


@router.get("/{account_id}/edit", response_class=HTMLResponse)
def edit_form(
    account_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return render(
            request,
            "partials/accounts/_form.html",
            account=None,
            action="",
            errors={"account": "not found"},
            status_code=404,
        )
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="Edit account",
        form_include="partials/accounts/_form.html",
        account=acc,
        action=f"/accounts/{account_id}",
        errors={},
    )


@router.post("/{account_id}")
def update_account(
    account_id: int,
    request: Request,
    *,
    name: str = Form(...),
    type: str = Form(""),
    is_liability: str = Form(""),
    credit_limit: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return render(
            request,
            "partials/accounts/_form.html",
            account=None,
            action="",
            errors={"account": "not found"},
            status_code=404,
        )
    parsed = parse_account_patch(
        acc, name=name, account_type=type, is_liability=is_liability, credit_limit=credit_limit
    )
    if parsed.patch is None:
        return render(
            request,
            "partials/accounts/_form.html",
            account=acc,
            action=f"/accounts/{account_id}",
            errors=parsed.errors,
            status_code=422,
        )
    accounts_service.update(conn, user_id, account_id, parsed.patch)
    html = render(
        request,
        "partials/accounts/_card.html",
        card=accounts_data.single_card(conn, user_id, account_id, settings),
    )
    trigger(html, Event.BALANCE_STALE)
    return html


@router.post("/{account_id}/delete")
def delete_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    accounts_service.archive_account(conn, user_id, account_id)
    resp = Response(content="", media_type="text/html")
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
        "partials/accounts/_snapshot_item.html",
        snapshot=snap,
        account=acc,
    )
    trigger(resp, toast=toast_payload("success", "Snapshot saved"))
    return resp


@router.get("/{account_id}/reconcile", response_class=HTMLResponse)
def reconcile_form(
    account_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return render(
            request,
            "partials/accounts/_reconcile_modal.html",
            account=None,
            derived=0,
            errors={"account": "not found"},
            status_code=404,
        )
    derived = balance_service.derive_balance(conn, user_id, account_id)
    modal: dict[str, Any] = accounts_data.reconcile_modal_context(conn, user_id, acc, derived)
    return render(
        request,
        "partials/accounts/_reconcile_modal.html",
        snapshots=accounts_data.recent_snapshots(conn, user_id, account_id),
        errors={},
        **modal,
    )


@router.post("/{account_id}/reconcile")
def reconcile_submit(
    account_id: int,
    request: Request,
    *,
    actual_balance: str = Form(...),
    category_id: str = Form(""),
    save_snapshot: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content="not found")
    derived = balance_service.derive_balance(conn, user_id, account_id)

    def _reject(message: str) -> Response:
        return render(
            request,
            "partials/accounts/_reconcile_modal.html",
            errors={"actual_balance": message},
            status_code=422,
            **accounts_data.reconcile_modal_context(conn, user_id, acc, derived),
        )

    entered = parse_amount_minor(actual_balance, acc.currency)
    if entered is None:
        return _reject("invalid number")
    try:
        reconcile_service.reconcile_account(
            conn,
            user_id,
            account_id=account_id,
            actual_balance_minor=reconcile_service.target_balance_minor(acc, entered),
            today=clock.today_local(settings),
            category_id=parse_category_id(category_id),
            save_snapshot=parse_save_snapshot(save_snapshot),
        )
    except (
        reconciliation_service.InvalidAvailableError,
        reconciliation_service.ValidationError,
    ) as exc:
        return _reject(str(exc))
    html = render(
        request,
        "partials/accounts/_row.html",
        card=accounts_data.single_card(conn, user_id, account_id, settings),
        today_date=clock.today_local(settings),
    )
    trigger(html, Event.BALANCE_STALE, Event.FORECAST_STALE)
    return html
