"""Accounts router (T-032).

Lists accounts with derived balance + stats, create/rename/soft-delete,
snapshot capture, and reconciliation. Business logic in services; this
router parses + renders.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.accounts import Account, NewAccount, PatchAccount
from budget_planner.domain.money import to_minor_units
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    snapshots as snapshots_repo,
)
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
    fortune as fortune_service,
    reconciliation as reconciliation_service,
)
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.htmx import trigger
from budget_planner.web.rendering import render

router = APIRouter(prefix="/accounts", tags=["accounts"])

_ISO_CCY_LEN = 3


def _today() -> date:
    return date.today()  # noqa: DTZ011 — intentional naive local date


_SPARKLINE_WIDTH = 120
_SPARKLINE_HEIGHT = 32


def _card_context(conn: sqlite3.Connection, user_id: int, account_id: int) -> dict[str, Any]:
    """Build the full context dict a single `_card.html` include needs."""
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    assert acc is not None
    bal = balance_service.derive_balance(conn, user_id, account_id)
    stats = balance_service.account_stats(conn, user_id, account_id)
    series = balance_service.balance_series(conn, user_id, account_id)
    series_values = [v for _, v in series]
    sparkline = balance_service.sparkline_points(
        series_values, width=_SPARKLINE_WIDTH, height=_SPARKLINE_HEIGHT
    )
    sparkline_area = (
        f"0,{_SPARKLINE_HEIGHT} {sparkline} {_SPARKLINE_WIDTH},{_SPARKLINE_HEIGHT}"
        if sparkline
        else ""
    )
    snapshots = snapshots_repo.list_for_account(conn, user_id, account_id)
    return {
        "account": acc,
        "balance": bal,
        "stats": stats,
        "series": series,
        "sparkline_points": sparkline,
        "sparkline_values": series_values,
        "sparkline_area_points": sparkline_area,
        "sparkline_width": _SPARKLINE_WIDTH,
        "sparkline_height": _SPARKLINE_HEIGHT,
        "snapshots": snapshots,
    }


def _hydrate(conn: sqlite3.Connection, user_id: int, settings: Settings) -> dict[str, Any]:
    accs = accounts_repo.list_all(conn, user_id)
    cards: list[dict[str, Any]] = [_card_context(conn, user_id, a.id) for a in accs]
    # ADR-0056 §7 — sort by balance desc; liabilities (negative balance) move
    # to the bottom. Assets land first, biggest first; liabilities land last,
    # smallest-liability-first so the credit card with the largest balance
    # sits closer to the assets block visually.
    cards.sort(
        key=lambda card: (
            0 if card["balance"] >= 0 else 1,
            -(card["balance"] if card["balance"] >= 0 else -card["balance"]),
        )
    )
    fortune = fortune_service.compute_fortune(conn, user_id, settings)
    return {
        "cards": cards,
        "fortune": fortune,
        "base_ccy": settings.base_currency,
        "totals_by_ccy": fortune.net_by_ccy,
        "fortune_base": fortune.net_base,
        "today_date": _today(),
    }


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    data = _hydrate(conn, user_id, settings)
    return render(request, "accounts/index.html", **data)


@router.get("/last-checked", response_class=HTMLResponse)
def last_checked(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """ADR-0056 §6 — latest snapshot or reconcile date per account.

    Powers the Accounts table "last checked" column + any inline
    freshness indicator. Pure read; no DB write.
    """
    rows = accounts_service.last_checked(conn, user_id)
    return render(
        request,
        "partials/accounts/_last_checked.html",
        rows=rows,
    )


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


def _parse_liability(raw: str) -> bool:
    return raw.strip().lower() in {"on", "true", "1"}


def _parse_credit_limit(raw: str, currency: str) -> tuple[int | None, str | None]:
    """Return (minor_units, error_message)."""
    trimmed = raw.strip()
    if not trimmed:
        return None, "positive credit limit required"
    try:
        dec = Decimal(trimmed)
    except InvalidOperation:
        return None, "positive credit limit required"
    if dec <= 0:
        return None, "positive credit limit required"
    return to_minor_units(dec, currency), None


@router.post("")
def create_account(  # noqa: PLR0917
    request: Request,
    name: str = Form(...),
    currency: str = Form(...),
    opening_balance: str = Form("0"),
    type: str = Form(""),
    is_liability: str = Form(""),
    credit_limit: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    errors: dict[str, str] = {}
    cur = currency.upper().strip()
    if len(cur) != _ISO_CCY_LEN or not cur.isalpha():
        errors["currency"] = "ISO 4217 code required"
    try:
        opening_dec = Decimal(opening_balance or "0")
    except InvalidOperation:
        errors["opening_balance"] = "invalid number"
        opening_dec = Decimal(0)
    if not name.strip():
        errors["name"] = "name required"
    liability = _parse_liability(is_liability)
    credit_limit_minor: int | None = None
    if liability and not errors.get("currency"):
        credit_limit_minor, limit_err = _parse_credit_limit(credit_limit, cur)
        if limit_err is not None:
            errors["credit_limit"] = limit_err
    if errors:
        return render(
            request,
            "partials/accounts/_form.html",
            account=None,
            action="/accounts",
            errors=errors,
            status_code=422,
        )
    opening = to_minor_units(opening_dec, cur)
    acc = accounts_repo.create(
        conn,
        user_id,
        NewAccount(
            name=name.strip(),
            currency=cur,
            opening_balance=opening,
            type=type or None,
            is_liability=liability,
            credit_limit_minor=credit_limit_minor,
        ),
    )
    html = render(
        request,
        "partials/accounts/_card.html",
        card=_card_context(conn, user_id, acc.id),
    )
    trigger(html, "balance-stale")
    return html


@router.get("/{account_id}/edit", response_class=HTMLResponse)
def edit_form(
    account_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
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
def update_account(  # noqa: PLR0917
    account_id: int,
    request: Request,
    name: str = Form(...),
    type: str = Form(""),
    is_liability: str = Form(""),
    credit_limit: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    if acc is None:
        return render(
            request,
            "partials/accounts/_form.html",
            account=None,
            action="",
            errors={"account": "not found"},
            status_code=404,
        )
    if not name.strip():
        return render(
            request,
            "partials/accounts/_form.html",
            account=acc,
            action=f"/accounts/{account_id}",
            errors={"name": "name required"},
            status_code=422,
        )
    liability = _parse_liability(is_liability)
    patch_limit: int | None = None
    clear_limit = False
    if liability:
        patch_limit, limit_err = _parse_credit_limit(credit_limit, acc.currency)
        if limit_err is not None:
            return render(
                request,
                "partials/accounts/_form.html",
                account=acc,
                action=f"/accounts/{account_id}",
                errors={"credit_limit": limit_err},
                status_code=422,
            )
    else:
        clear_limit = True
    accounts_repo.update(
        conn,
        user_id,
        account_id,
        PatchAccount(
            name=name.strip(),
            type=type or None,
            is_liability=liability,
            credit_limit_minor=patch_limit,
            clear_credit_limit=clear_limit,
        ),
    )
    updated = accounts_repo.find_by_id(conn, user_id, account_id)
    assert updated is not None
    html = render(
        request,
        "partials/accounts/_card.html",
        card=_card_context(conn, user_id, account_id),
    )
    trigger(html, "balance-stale")
    return html


@router.post("/{account_id}/delete")
def delete_account(
    account_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    accounts_repo.soft_delete(conn, user_id, account_id)
    resp = Response(content="", media_type="text/html")
    resp.headers["HX-Trigger"] = json.dumps(
        {
            "balance-stale": True,
            "forecast-stale": True,
            "toast": {"kind": "success", "message": "Account deleted"},
        }
    )
    return resp


@router.post("/{account_id}/snapshot")
def take_snapshot(
    account_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content="not found")
    bal = balance_service.derive_balance(conn, user_id, account_id)
    snap = snapshots_repo.create(
        conn, user_id, NewAccountSnapshot(account_id=account_id, balance=bal, note="user snapshot")
    )
    resp = render(
        request,
        "partials/accounts/_snapshot_item.html",
        snapshot=snap,
        account=acc,
    )
    resp.headers["HX-Trigger"] = json.dumps(
        {"toast": {"kind": "success", "message": "Snapshot saved"}}
    )
    return resp


def _uses_available(acc: Account) -> bool:
    """T-D52 — liability with a credit limit reconciles by available credit."""
    return bool(acc.is_liability and acc.credit_limit_minor)


def _available_mode_context(acc: Account, derived: int) -> dict[str, Any]:
    if not _uses_available(acc):
        return {"by_available": False}
    limit = acc.credit_limit_minor or 0
    used = max(-derived, 0)
    return {
        "by_available": True,
        "credit_limit_minor": limit,
        "used_minor": used,
        "available_minor": max(limit - used, 0),
    }


@router.get("/{account_id}/reconcile", response_class=HTMLResponse)
def reconcile_form(
    account_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
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
    snapshots = snapshots_repo.list_for_account(conn, user_id, account_id)
    categories = [c for c in categories_repo.list_all(conn, user_id) if not c.is_system]
    reconciliation_cat = categories_repo.find_by_name(conn, user_id, "Reconciliation")
    return render(
        request,
        "partials/accounts/_reconcile_modal.html",
        account=acc,
        derived=derived,
        snapshots=snapshots[:5],
        categories=categories,
        reconciliation_cat=reconciliation_cat,
        errors={},
        **_available_mode_context(acc, derived),
    )


@router.post("/{account_id}/reconcile")
def reconcile_submit(  # noqa: PLR0917
    account_id: int,
    request: Request,
    actual_balance: str = Form(...),
    category_id: str = Form(""),
    save_snapshot: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    if acc is None:
        return Response(status_code=404, content="not found")
    derived = balance_service.derive_balance(conn, user_id, account_id)

    def _reject(message: str) -> Response:
        return render(
            request,
            "partials/accounts/_reconcile_modal.html",
            account=acc,
            derived=derived,
            categories=[c for c in categories_repo.list_all(conn, user_id) if not c.is_system],
            reconciliation_cat=categories_repo.find_by_name(conn, user_id, "Reconciliation"),
            errors={"actual_balance": message},
            status_code=422,
            **_available_mode_context(acc, derived),
        )

    try:
        actual = Decimal(actual_balance.replace(",", ".").strip())
    except InvalidOperation:
        return _reject("invalid number")
    actual_minor = to_minor_units(actual, acc.currency)
    if _uses_available(acc):
        try:
            actual_minor = reconciliation_service.available_to_target_balance(
                acc.credit_limit_minor or 0, actual_minor
            )
        except reconciliation_service.InvalidAvailableError as exc:
            return _reject(str(exc))
    chosen_cat_id: int | None = None
    if category_id.strip():
        try:
            chosen_cat_id = int(category_id)
        except ValueError:
            chosen_cat_id = None
    with contextlib.suppress(reconciliation_service.NoAdjustmentNeededError):
        reconciliation_service.reconcile(
            conn, user_id, account_id, actual_minor, _today(), category_id=chosen_cat_id
        )
    if save_snapshot.strip().lower() in ("1", "on", "true", "yes"):
        bal = balance_service.derive_balance(conn, user_id, account_id)
        snapshots_repo.create(
            conn,
            user_id,
            NewAccountSnapshot(account_id=account_id, balance=bal, note="reconcile snapshot"),
        )
    html = render(
        request,
        "partials/accounts/_row.html",
        card=_card_context(conn, user_id, account_id),
        today_date=_today(),
    )
    trigger(html, "balance-stale", "forecast-stale")
    return html
