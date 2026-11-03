"""Transactions router (T-031).

Thin HTTP surface over `repositories.transactions` + `services.export`.
Parses form input, calls the service / repo, renders Jinja fragments.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import parse_amount_str, to_minor_units
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    TransactionFilter,
)
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    balance as balance_service,
    export as export_service,
)
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.htmx import trigger
from budget_planner.web.rendering import render


@dataclass(frozen=True, slots=True)
class LimitPreview:
    """Projected utilisation snapshot for the transaction form (ADR-0024)."""

    projected_balance: int
    available_after: int
    used_after: int
    limit: int
    over_by: int
    currency: str


router = APIRouter(prefix="/transactions", tags=["transactions"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_filter(request: Request) -> TransactionFilter:
    """Parse the shared filter query params. Public — reused by T-038."""
    q = request.query_params
    account_id = _parse_int(q.get("account_id"))
    category_id = _parse_int(q.get("category_id"))
    description = q.get("q") or None
    return TransactionFilter(
        date_from=_parse_date(q.get("date_from")),
        date_to=_parse_date(q.get("date_to")),
        account_ids=(account_id,) if account_id is not None else (),
        category_ids=(category_id,) if category_id is not None else (),
        amount_min=_parse_int(q.get("min_amount")),
        amount_max=_parse_int(q.get("max_amount")),
        description_contains=description,
    )


def _hydrate_rows(conn: sqlite3.Connection, user_id: int, rows: list[Any]) -> list[dict[str, Any]]:
    cats = {c.id: c for c in categories_repo.list_all(conn, user_id, include_deleted=True)}
    accts = {a.id: a for a in accounts_repo.list_all(conn, user_id, include_deleted=True)}
    out: list[dict[str, Any]] = []
    for r in rows:
        cat = cats.get(r.category_id)
        acc = accts.get(r.account_id)
        dest = accts.get(r.dest_account_id) if r.dest_account_id is not None else None
        out.append(
            {
                "id": r.id,
                "operation_date": r.operation_date,
                "amount": r.amount,
                "description": r.description,
                "category": cat,
                "account": acc,
                "dest_account": dest,
                "currency": acc.currency if acc else "",
            }
        )
    return out


@router.get("")
def list_page() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the unified ledger with the ``actual`` view selected. Kept at
    ``302`` for one release per ADR-0023; a follow-up task flips to ``301``.
    The HTMX fragment alias ``/transactions/table`` and the CRUD sub-routes
    (``/transactions/new``, ``/transactions/{id}/edit``, etc.) remain live.
    """
    return RedirectResponse(url="/ledger?view=actual", status_code=302)


def _compute_limit_preview(
    conn: sqlite3.Connection, user_id: int, account_id: int, category_id: int, amount_raw: str
) -> LimitPreview | None:
    """Project post-transaction utilization for a liability account.

    Soft-failing by design: any missing/unparseable input returns ``None`` so
    the fragment stays blank and the user can keep editing (ADR-0024).
    """
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    if acc is None or not acc.is_liability or acc.credit_limit_minor is None:
        return None
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if cat is None:
        return None
    dec = parse_amount_str(amount_raw, acc.currency)
    if dec is None or dec <= 0:
        return None
    amount_minor = to_minor_units(dec, acc.currency)
    current = balance_service.derive_balance(conn, user_id, account_id)
    direction = cat.direction
    if direction is Direction.INCOME:
        delta = amount_minor
    elif direction is Direction.EXPENSE or direction is Direction.TRANSIT:
        delta = -amount_minor
    else:
        delta = amount_minor
    projected = current + delta
    limit = acc.credit_limit_minor
    used_after = max(-projected, 0)
    available_after = max(limit - used_after, 0)
    over_by = max(used_after - limit, 0)
    return LimitPreview(
        projected_balance=projected,
        available_after=available_after,
        used_after=used_after,
        limit=limit,
        over_by=over_by,
        currency=acc.currency,
    )


@router.get("/_limit_preview", response_class=HTMLResponse)
def limit_preview(  # noqa: PLR0917
    request: Request,
    account_id: str = "",
    category_id: str = "",
    amount: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    acc_id = _parse_int(account_id)
    cat_id = _parse_int(category_id)
    preview: LimitPreview | None = None
    if acc_id is not None and cat_id is not None:
        preview = _compute_limit_preview(conn, user_id, acc_id, cat_id, amount)
    return render(request, "partials/transactions/_limit_preview.html", preview=preview)


@router.get("/table", response_class=HTMLResponse)
def table_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Legacy fragment alias (T-064).

    Delegates to the unified ledger fragment with ``view=actual`` so pre-T-064
    HTMX scripts keep working. The response shape (``#txn-table`` container,
    row ids ``#txn-{id}``) is preserved by the ledger template.
    """
    from budget_planner.web.routers.ledger import render_table_for  # noqa: PLC0415

    return render_table_for(request, conn, user_id, "actual")


@router.get("/new", response_class=HTMLResponse)
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
        "partials/_slideover.html",
        slide_over_title="New transaction",
        form_include="partials/transactions/_form.html",
        action="/transactions",
        method="post",
        txn=None,
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        errors={},
    )


def _validate_amount(amount: str, currency: str) -> tuple[int | None, str | None]:
    # T-124 / ADR-0040 — accept both `,` and `.` as decimal separators and
    # cap fractional digits at the currency's minor-unit scale (two for
    # PLN/EUR/USD, zero for JPY/KRW), mirroring the UI contract in
    # `numeric-input.js`.
    dec = parse_amount_str(amount, currency)
    if dec is None:
        return None, "amount must be a decimal number"
    if dec <= 0:
        return None, "amount must be positive"
    minor = to_minor_units(dec, currency)
    return minor, None


@router.post("")
def create_txn(  # noqa: PLR0917
    request: Request,
    operation_date: str = Form(...),
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    dest_account_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),  # noqa: ARG001
    user_id: int = Depends(current_user_id),
) -> Response:
    errors: dict[str, str] = {}
    op_date = _parse_date(operation_date)
    if op_date is None:
        errors["operation_date"] = "invalid date"
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    minor: int | None = None
    if acc is not None:
        minor, err = _validate_amount(amount, acc.currency)
        if err is not None:
            errors["amount"] = err
    dest_id: int | None = None
    if dest_account_id and cat is not None and cat.direction == Direction.TRANSIT:
        parsed = _parse_int(dest_account_id)
        if parsed is None:
            errors["dest_account_id"] = "invalid destination"
        else:
            dest = accounts_repo.find_by_id(conn, user_id, parsed)
            if dest is None:
                errors["dest_account_id"] = "unknown destination"
            elif acc is not None and dest.currency != acc.currency:
                errors["dest_account_id"] = "cross-currency transit not supported"
            else:
                dest_id = parsed

    if errors:
        return render(
            request,
            "partials/transactions/_form.html",
            action="/transactions",
            method="post",
            txn=None,
            categories=categories_repo.list_all(conn, user_id),
            accounts=accounts_repo.list_all(conn, user_id),
            errors=errors,
            status_code=422,
        )

    assert op_date is not None and minor is not None
    new_txn = transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=op_date,
            category_id=category_id,
            account_id=account_id,
            amount=minor,
            description=description,
            dest_account_id=dest_id,
        ),
    )
    row = _hydrate_rows(conn, user_id, [new_txn])[0]
    html = render(
        request,
        "partials/transactions/_row.html",
        txn=row,
    )
    trigger(html, "balance-stale", "forecast-stale", "ledger-stale")
    return html


@router.get("/{txn_id}/edit", response_class=HTMLResponse)
def edit_form(
    txn_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    txn = transactions_repo.find_by_id(conn, user_id, txn_id)
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
        "partials/_slideover.html",
        slide_over_title="Edit transaction",
        form_include="partials/transactions/_form.html",
        action=f"/transactions/{txn_id}",
        method="post",
        txn=txn,
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        errors={},
    )


@router.post("/{txn_id}")
def update_txn(  # noqa: PLR0917
    txn_id: int,
    request: Request,
    operation_date: str = Form(...),
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    dest_account_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    existing = transactions_repo.find_by_id(conn, user_id, txn_id)
    if existing is None:
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
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    errors: dict[str, str] = {}
    op_date = _parse_date(operation_date)
    if op_date is None:
        errors["operation_date"] = "invalid date"
    if acc is None:
        errors["account_id"] = "unknown account"
    minor: int | None = None
    if acc is not None:
        minor, err = _validate_amount(amount, acc.currency)
        if err is not None:
            errors["amount"] = err
    if errors:
        return render(
            request,
            "partials/transactions/_form.html",
            action=f"/transactions/{txn_id}",
            method="post",
            txn=existing,
            categories=categories_repo.list_all(conn, user_id),
            accounts=accounts_repo.list_all(conn, user_id),
            errors=errors,
            status_code=422,
        )
    assert op_date is not None and minor is not None
    dest_id_val = _parse_int(dest_account_id) if dest_account_id else None
    transactions_repo.update(
        conn,
        user_id,
        txn_id,
        PatchTransaction(
            operation_date=op_date,
            category_id=category_id,
            account_id=account_id,
            amount=minor,
            description=description,
            dest_account_id=dest_id_val,
        ),
    )
    updated = transactions_repo.find_by_id(conn, user_id, txn_id)
    assert updated is not None
    row = _hydrate_rows(conn, user_id, [updated])[0]
    html = render(request, "partials/transactions/_row.html", txn=row)
    trigger(html, "balance-stale", "forecast-stale", "ledger-stale")
    return html


@router.post("/{txn_id}/delete")
def delete_txn(
    txn_id: int, conn: sqlite3.Connection = Depends(get_db), user_id: int = Depends(current_user_id)
) -> Response:
    transactions_repo.soft_delete(conn, user_id, txn_id)
    resp = Response(content="", media_type="text/html")
    trigger(resp, "balance-stale", "forecast-stale", "ledger-stale")
    return resp


@router.post("/{txn_id}/restore")
def restore_txn(
    txn_id: int, conn: sqlite3.Connection = Depends(get_db), user_id: int = Depends(current_user_id)
) -> Response:
    """T-R70 — undo a soft-delete (ADR-0019)."""
    try:
        transactions_repo.undelete(conn, user_id, txn_id)
    except LookupError:
        return Response(status_code=404, content="not found")
    resp = Response(content="", media_type="text/html")
    trigger(resp, "balance-stale", "forecast-stale", "ledger-stale")
    return resp


@router.get("/export")
def export(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    fmt = request.query_params.get("format", "csv")
    flt = parse_filter(request)
    rows = transactions_repo.list_filtered(conn, user_id, flt)
    hydrated = _hydrate_rows(conn, user_id, rows)
    export_rows: list[dict[str, Any]] = [
        {
            "id": r["id"],
            "operation_date": r["operation_date"],
            "amount_minor": r["amount"],
            "currency": r["currency"],
            "description": r["description"] or "",
            "category": r["category"].name if r["category"] else "",
            "account": r["account"].name if r["account"] else "",
            "dest_account": r["dest_account"].name if r["dest_account"] else "",
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
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    if fmt == "parquet":
        body = export_service.export_parquet(export_rows, columns)
        return Response(
            content=body,
            media_type="application/vnd.apache.parquet",
            headers={"Content-Disposition": f'attachment; filename="transactions_{stamp}.parquet"'},
        )
    body = export_service.export_csv(export_rows, columns)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="transactions_{stamp}.csv"'},
    )
