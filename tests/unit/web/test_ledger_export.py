"""T-UR34b: the per-tab export link builder."""

from __future__ import annotations

from datetime import date

from budget_planner.web.ledger_export import ExportLinks, export_links
from budget_planner.web.ledger_types import LedgerFilters


def test_actual_links_carry_every_filter() -> None:
    f = LedgerFilters(
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        account_ids=(3,),
        category_ids=(7,),
        direction="expense",
        search="a b&c",
        page=4,
    )
    assert export_links("actual", f) == ExportLinks(
        csv="/transactions/export?date_from=2026-10-01&date_to=2026-10-31&account_id=3"
        "&category_id=7&direction=expense&q=a+b%26c&format=csv",
        parquet="/transactions/export?date_from=2026-10-01&date_to=2026-10-31&account_id=3"
        "&category_id=7&direction=expense&q=a+b%26c&format=parquet",
    )


def test_planned_links_without_filters() -> None:
    assert export_links("planned", LedgerFilters()) == ExportLinks(
        csv="/planned/export?format=csv", parquet="/planned/export?format=parquet"
    )


def test_recurring_has_no_export() -> None:
    assert export_links("recurring", LedgerFilters()) is None
