"""Ledger page data assembly (T-064, T-Q265).

Filter parsing, row hydration and template-context building for the unified
``/ledger`` page and its fragments. Services compute; this module only reads
them through service entry points and names the template keys (ADR-0142), so
the router stays parse, call, render (ADR-0130).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Final

from fastapi import Request
from fastapi.responses import HTMLResponse

from budget_planner.config import Settings
from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.limits import PAGE_SIZE_MAX
from budget_planner.domain.planned import PlannedFilter, PlannedTransaction
from budget_planner.domain.recurring import RecurringRule
from budget_planner.domain.transactions import Transaction, TransactionFilter
from budget_planner.services import (
    account_planned as account_planned_service,
    accounts as accounts_service,
    categories as categories_service,
    fx as fx_service,
    ledger_totals,
    planned as planned_service,
    recurring as recurring_service,
    recurring_formula as formula_svc,
    transactions as transactions_service,
)
from budget_planner.web.ledger_types import LedgerFilters, ViewKind, view_kinds
from budget_planner.web.params import query_choice, query_date, query_int
from budget_planner.web.rendering import render_context

_PAGE_SIZE_DEFAULT: Final = 50
_DIRECTIONS: Final = tuple(d.value for d in Direction)
_SCOPES: Final = ("all", "unpromoted")
_PLANNED_LOOKBACK: Final = timedelta(days=30)
_PLANNED_LOOKAHEAD: Final = timedelta(days=180)

Row = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class TxnRow:
    """One hydrated transaction row for the ledger Actual view and the entry-row partial."""

    id: int
    operation_date: date
    amount: int
    description: str | None
    category: Category | None
    account: Account | None
    dest_account: Account | None
    currency: str


def parse_filters(request: Request) -> LedgerFilters:
    """Parse the shared ledger filter from the request's query params."""
    q = request.query_params
    account_id = query_int("account_id", q.get("account_id"))
    category_id = query_int("category_id", q.get("category_id"))
    page = max(1, query_int("page", q.get("page")) or 1)
    size = query_int("page_size", q.get("page_size")) or _PAGE_SIZE_DEFAULT
    size = max(1, min(size, PAGE_SIZE_MAX))
    return LedgerFilters(
        date_from=query_date("date_from", q.get("date_from")),
        date_to=query_date("date_to", q.get("date_to")),
        account_ids=(account_id,) if account_id is not None else (),
        category_ids=(category_id,) if category_id is not None else (),
        direction=query_choice("direction", q.get("direction"), _DIRECTIONS),
        search=q.get("q") or None,
        page=page,
        page_size=size,
    )


def txn_filter(filters: LedgerFilters) -> TransactionFilter:
    """The one mapping from the shared ledger filter to a transaction filter (list and export)."""
    return TransactionFilter(
        date_from=filters.date_from,
        date_to=filters.date_to,
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        directions=_direction_tuple(filters.direction),
        description_contains=filters.search,
    )


def planned_filter(
    filters: LedgerFilters, today: date, *, promoted: bool | None = None
) -> PlannedFilter:
    """The one mapping from the shared ledger filter to the Planned tab's filter.

    Without dates the window is the pending backlog plus the forward window
    ``[today-30d, today+180d]`` (not the service's calendar-month default), for
    both the list and the export.
    """
    return PlannedFilter(
        date_from=filters.date_from or (today - _PLANNED_LOOKBACK),
        date_to=filters.date_to or (today + _PLANNED_LOOKAHEAD),
        account_ids=filters.account_ids,
        category_ids=filters.category_ids,
        directions=_direction_tuple(filters.direction),
        description_contains=filters.search,
        promoted=promoted,
    )


def parse_txn_filter(request: Request) -> TransactionFilter:
    """Parse the transaction export filter: the ledger filter plus the amount bounds."""
    q = request.query_params
    return replace(
        txn_filter(parse_filters(request)),
        amount_min=query_int("min_amount", q.get("min_amount")),
        amount_max=query_int("max_amount", q.get("max_amount")),
    )


def parse_planned_filter(request: Request, today: date) -> PlannedFilter:
    """Parse the planned export filter (``scope=unpromoted`` narrows), as the Planned tab does."""
    scope = query_choice("scope", request.query_params.get("scope"), _SCOPES)
    return planned_filter(
        parse_filters(request), today, promoted=False if scope == "unpromoted" else None
    )


def _lookups(
    conn: sqlite3.Connection, user_id: int
) -> tuple[dict[int, Category], dict[int, Account]]:
    cats = {c.id: c for c in categories_service.list_all(conn, user_id, include_deleted=True)}
    accts = {a.id: a for a in accounts_service.list_all(conn, user_id, include_deleted=True)}
    return cats, accts


def hydrate_txn_rows(
    conn: sqlite3.Connection, user_id: int, rows: Sequence[Transaction]
) -> list[TxnRow]:
    """Attach category and account objects to transactions for display and export."""
    cats, accts = _lookups(conn, user_id)
    out: list[TxnRow] = []
    for r in rows:
        acc = accts.get(r.account_id)
        out.append(
            TxnRow(
                id=r.id,
                operation_date=r.operation_date,
                amount=r.amount,
                description=r.description,
                category=cats.get(r.category_id),
                account=acc,
                dest_account=accts.get(r.dest_account_id)
                if r.dest_account_id is not None
                else None,
                currency=acc.currency if acc else "",
            )
        )
    return out


def planned_row_from_persisted(
    pl: PlannedTransaction, acc: Account | None, cat: Category | None
) -> dict[str, object]:
    """Row view of a just-created planned transaction for ``_row.html``."""
    return {
        "key": f"p-{pl.id}",
        "kind": "persisted",
        "operation_date": pl.operation_date,
        "amount_minor": pl.amount,
        "description": pl.description,
        "is_promoted": pl.promoted_to_txn_id is not None,
        "account": acc,
        "category": cat,
        "persisted_id": pl.id,
        "currency": acc.currency if acc else "",
    }


def _planned_key(view: planned_service.PlannedView) -> str:
    if view.persisted_id is not None:
        return f"p-{view.persisted_id}"
    return f"v-{view.recurring_rule_id}-{view.operation_date.strftime('%Y%m%d')}"


def _hydrate_planned_rows(
    conn: sqlite3.Connection,
    user_id: int,
    views: Sequence[planned_service.PlannedView],
    today: date | None = None,
) -> list[dict[str, object]]:
    cats, accts = _lookups(conn, user_id)
    out: list[dict[str, object]] = []
    for v in views:
        acc = accts.get(v.account_id)
        out.append(
            {
                "key": _planned_key(v),
                "kind": v.kind,
                "operation_date": v.operation_date,
                "amount_minor": v.amount_minor,
                "description": v.description,
                "is_promoted": v.is_promoted,
                "persisted_id": v.persisted_id,
                "recurring_rule_id": v.recurring_rule_id,
                "account": acc,
                "category": cats.get(v.category_id),
                "currency": acc.currency if acc else "",
                "status": ledger_totals.planned_status(v.operation_date, today)
                if today is not None and not v.is_promoted
                else None,
            }
        )
    return out


def _on_live_account(row: dict[str, object]) -> bool:
    """Planned totals skip rows of soft-deleted accounts; the list keeps them (ADR-0136)."""
    acc = row.get("account")
    return isinstance(acc, Account) and acc.deleted_at is None


def _in_date_range(day: date, filters: LedgerFilters) -> bool:
    return not (filters.date_from and day < filters.date_from) and not (
        filters.date_to and day > filters.date_to
    )


def _in_ids(value: int, ids: tuple[int, ...]) -> bool:
    return not ids or value in ids


def _rule_matches(rule: RecurringRule, cat: Category | None, filters: LedgerFilters) -> bool:
    """V.34 client-side filters; the date range matches against ``next_due``."""
    if not _in_date_range(rule.next_due, filters):
        return False
    if not (
        _in_ids(rule.account_id, filters.account_ids)
        and _in_ids(rule.category_id, filters.category_ids)
    ):
        return False
    if filters.direction and (cat is None or cat.direction.value != filters.direction):
        return False
    return not filters.search or filters.search.lower() in (rule.default_description or "").lower()


def _recurring_row(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    refs: tuple[Account | None, Category | None],
    formula_fx: formula_svc.FormulaFx,
) -> dict[str, object]:
    acc, cat = refs
    overrides = recurring_service.list_overrides(conn, user_id, rule.id)
    # T-122: the override (if any) on the current `next_due` bolds / italicises its cells.
    override = next((ov for ov in overrides if ov.occurrence_date == rule.next_due), None)
    # Formula-aware default (ADR-0045); overrides win per ADR-0038 precedence.
    effective = formula_svc.resolve_rule_amount(conn, user_id, rule, rule.next_due, fx=formula_fx)
    amount_overridden = override is not None and override.amount_override is not None
    if override is not None and override.amount_override is not None:
        effective = override.amount_override
    return {
        "id": rule.id,
        "cadence": rule.cadence,
        "start_date": rule.start_date,
        "end_date": rule.end_date,
        "next_due": rule.next_due,
        "default_amount": rule.default_amount,
        "default_description": rule.default_description,
        "active": rule.active,
        "account": acc,
        "category": cat,
        "overrides": overrides,
        "override_deltas": {
            ov.occurrence_date: ledger_totals.override_delta(
                formula_svc.resolve_rule_amount(
                    conn, user_id, rule, ov.occurrence_date, fx=formula_fx
                ),
                ov.amount_override,
            )
            for ov in overrides
            if ov.amount_override is not None
        },
        "override_on_next_due": override,
        "override_present": override is not None,
        "amount_overridden": amount_overridden,
        "effective_amount_minor": effective,
        "amount_formula": rule.amount_formula,
        "is_formula": rule.amount_formula is not None,
        "currency": acc.currency if acc else "",
    }


def _recurring_rows(
    conn: sqlite3.Connection,
    user_id: int,
    filters: LedgerFilters,
    fx: fx_service.FxConverter,
) -> list[dict[str, object]]:
    # Ledger Recurring tab lists only live rules (ADR-0038 §Ledger-UI):
    # Delete behaviourally deactivates, which must remove the row from view.
    rules = sorted(
        recurring_service.list_rules(conn, user_id, active_only=True),
        key=lambda r: (r.next_due, r.id),
    )
    cats, accts = _lookups(conn, user_id)
    # Formula sources convert across currencies (T-Q215, ADR-0139): cache-only rates.
    formula_fx = formula_svc.formula_fx(conn, user_id, fx)
    return [
        _recurring_row(
            conn,
            user_id,
            rule,
            (accts.get(rule.account_id), cats.get(rule.category_id)),
            formula_fx,
        )
        for rule in rules
        if _rule_matches(rule, cats.get(rule.category_id), filters)
    ]


def _direction_tuple(raw: str | None) -> tuple[Direction, ...]:
    """Map the string filter from the chip select to a `Direction` tuple.

    Empty / unknown value → no filter. V.34 — fixes the dead Direction chip.
    """
    if not raw:
        return ()
    try:
        return (Direction(raw),)
    except ValueError:
        return ()


def _actual_rows(conn: sqlite3.Connection, user_id: int, filters: LedgerFilters) -> list[TxnRow]:
    txn_filter_ = replace(
        txn_filter(filters),
        limit=filters.page_size,
        offset=(filters.page - 1) * filters.page_size,
        order_desc=True,
    )
    return hydrate_txn_rows(
        conn, user_id, transactions_service.list_filtered(conn, user_id, txn_filter_)
    )


def _ledger_day_nets(
    conn: sqlite3.Connection, settings: Settings, rows: Sequence[TxnRow]
) -> dict[str, int | None]:
    """Per-day net for the Actual view via ``ledger_totals.actual_day_nets`` (ADR-0008, T-D48)."""
    items = [
        (r.operation_date, r.amount, r.category.direction if r.category else None, r.currency)
        for r in rows
    ]
    # Cached rates only (ADR-0139): rendering never touches the network. Each row
    # converts at its own day's rate; the reference day is the newest one shown.
    fx = fx_service.converter_for(conn, settings, max((i[0] for i in items), default=date.min))
    return ledger_totals.actual_day_nets(
        items, lambda amount, day, ccy: fx.to_base(amount, ccy, day)
    )


def _planned_rows(
    conn: sqlite3.Connection, user_id: int, filters: LedgerFilters, today: date
) -> list[dict[str, object]]:
    views = planned_service.list_planned(conn, user_id, planned_filter(filters, today), today=today)
    return _hydrate_planned_rows(conn, user_id, views, today)


@dataclass(frozen=True, slots=True, kw_only=True)
class FilterSummary:
    """Structured description of the active ledger filters for the no-matches state (T-UR34c)."""

    category_names: tuple[str, ...] = ()
    account_names: tuple[str, ...] = ()
    direction: str | None = None
    search: str | None = None
    date_from: date | None = None
    date_to: date | None = None

    @property
    def is_active(self) -> bool:
        """True when at least one filter narrows the list."""
        return bool(
            self.category_names
            or self.account_names
            or self.direction
            or self.search
            or self.date_from
            or self.date_to
        )


def filter_summary(
    filters: LedgerFilters,
    categories: Mapping[int, Category],
    accounts: Mapping[int, Account],
) -> FilterSummary:
    """Describe the active filters by name (unknown ids are skipped); no formatting."""
    return FilterSummary(
        category_names=tuple(categories[i].name for i in filters.category_ids if i in categories),
        account_names=tuple(accounts[i].name for i in filters.account_ids if i in accounts),
        direction=filters.direction,
        search=filters.search,
        date_from=filters.date_from,
        date_to=filters.date_to,
    )


def period_spent_minor(
    conn: sqlite3.Connection, user_id: int, settings: Settings, today: date
) -> int | None:
    """Actual hero "spent this period": expenses in the Budget/Today pay window, base currency.

    The window is resolved as Budget and Today resolve it (``resolve_period_start`` +
    ``fiscal_window``, ADR-0151 section 2), not the calendar month.

    ``None`` when a needed FX rate is not cached (the hero omits a wrong figure).
    """
    window = account_planned_service.resolve_window(conn, user_id, today)
    rows = hydrate_txn_rows(
        conn,
        user_id,
        transactions_service.list_filtered(
            conn,
            user_id,
            TransactionFilter(
                date_from=window.start,
                date_to=window.last_day,
                directions=(Direction.EXPENSE,),
                live_accounts_only=True,
            ),
        ),
    )
    fx = fx_service.converter_for(conn, settings, today)
    items = [
        (r.operation_date, r.amount, r.category.direction if r.category else None, r.currency)
        for r in rows
    ]
    return ledger_totals.spent_minor(items, lambda amount, day, ccy: fx.to_base(amount, ccy, day))


def _tab_counts(conn: sqlite3.Connection, user_id: int) -> dict[str, int]:
    """Ledger tab counts (ADR-0056 §4): total actual + unpromoted planned +
    active recurring. Keeps logic in one place so the shell + fragments
    always display the same number.
    """
    return {
        "actual": transactions_service.count_filtered(conn, user_id),
        "planned": len(planned_service.list_filtered(conn, user_id, PlannedFilter(promoted=False))),
        "recurring": len(recurring_service.list_rules(conn, user_id, active_only=True)),
    }


def _page_keys(
    view: ViewKind, rows: Sequence[object], filters: LedgerFilters, today: date
) -> dict[str, object]:
    return {
        "view": view,
        "rows": rows,
        "page": filters.page,
        "page_size": filters.page_size,
        "has_next": view == "actual" and len(rows) == filters.page_size,
        "today_date": today,
    }


def table_context(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    settings: Settings,
    view: ViewKind,
    filters: LedgerFilters,
    today: date,
) -> dict[str, object]:
    """Template keys for the ``/ledger/table`` fragment."""
    rows: Sequence[object]
    day_nets: dict[str, int | None] = {}
    if view == "actual":
        actual = _actual_rows(conn, user_id, filters)
        rows, day_nets = actual, _ledger_day_nets(conn, settings, actual)
    elif view == "planned":
        rows = _planned_rows(conn, user_id, filters, today)
    else:
        fx = fx_service.converter_for(conn, settings, today)
        rows = _recurring_rows(conn, user_id, filters, fx)
    cats = {c.id: c for c in categories_service.list_all(conn, user_id, include_deleted=True)}
    return {
        **_page_keys(view, rows, filters, today),
        "day_nets": day_nets,
        "categories_by_id": cats,
    }


def render_table_for(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    settings: Settings,
    view: ViewKind,
    today: date,
) -> HTMLResponse:
    """Render the ledger table fragment for ``view`` (shared by the legacy fragment aliases)."""
    ctx = table_context(
        conn, user_id, settings=settings, view=view, filters=parse_filters(request), today=today
    )
    return render_context(request, "ledger/_table.html", ctx)


def _lookup_keys(
    conn: sqlite3.Connection, user_id: int, filters: LedgerFilters
) -> dict[str, object]:
    """Category and account lists, the id lookup and the no-matches filter summary."""
    cats_all = categories_service.list_all(conn, user_id, include_deleted=True)
    accts_all = accounts_service.list_all(conn, user_id, include_deleted=True)
    return {
        "categories": categories_service.list_all(conn, user_id),
        "accounts": accounts_service.list_all(conn, user_id),
        "categories_by_id": {c.id: c for c in cats_all},
        "filter_summary": filter_summary(
            filters, {c.id: c for c in cats_all}, {a.id: a for a in accts_all}
        ),
    }


def index_context(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    settings: Settings,
    view: ViewKind,
    filters: LedgerFilters,
    today: date,
) -> dict[str, object]:
    """Template keys for the ``/ledger`` page shell."""
    rows: Sequence[object]
    day_nets: dict[str, int | None] = {}
    recurring_summary: ledger_totals.RecurringTotals | None = None
    planned_summary: ledger_totals.PlannedTotals | None = None
    base_ccy = settings.base_currency
    fx = fx_service.converter_for(conn, settings, today)
    spent: int | None = None
    if view == "actual":
        actual = _actual_rows(conn, user_id, filters)
        rows, day_nets = actual, _ledger_day_nets(conn, settings, actual)
        spent = period_spent_minor(conn, user_id, settings, today)
    elif view == "planned":
        planned = _planned_rows(conn, user_id, filters, today)
        planned_summary = ledger_totals.planned_totals(
            [r for r in planned if _on_live_account(r)],
            base_ccy,
            lambda amount, day, ccy: fx.to_base(amount, ccy, day),
            today,
        )
        rows = planned
    else:
        recurring = _recurring_rows(conn, user_id, filters, fx)
        recurring_summary = ledger_totals.recurring_monthly_totals(
            recurring, base_ccy, lambda amount, day, ccy: fx.to_base(amount, ccy, day)
        )
        rows = recurring
    return {
        **_page_keys(view, rows, filters, today),
        **_lookup_keys(conn, user_id, filters),
        "spent_minor": spent,
        "views": view_kinds(),
        "day_nets": day_nets,
        "filters": filters,
        "tab_counts": _tab_counts(conn, user_id),
        "recurring_summary": recurring_summary,
        "planned_summary": planned_summary,
    }
