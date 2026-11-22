"""Per-category budget lines for the month summary (pure; extracted from ``budget``).

Turns the already-computed per-category sums into ``CategoryBudgetLine`` rows.
No I/O, no clock: the caller (``services.budget.month_summary``) does the reads.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.services.aggregates import mean_minor


@dataclass(frozen=True, slots=True)
class CategoryBudgetLine:
    category_id: int
    category_name: str
    category_direction: Direction
    category_color: str | None
    budgeted_minor: int | None
    spent_minor: int
    remaining_minor: int | None
    avg_monthly_overall_minor: int
    avg_this_year_minor: int
    delta_vs_prev_month_minor: int


@dataclass(frozen=True, slots=True)
class CategorySums:
    """Per-category base-currency sums feeding the budget lines."""

    spent_this: dict[int, int]
    spent_prev: dict[int, int]
    year_sums: dict[int, int]
    overall_sum: dict[int, int]
    overall_months: dict[int, int]
    elapsed_in_year: int


def build_budget_lines(
    cats: Sequence[Category],
    budgets_by_cat: Mapping[int, int | None],
    sums: CategorySums,
) -> list[CategoryBudgetLine]:
    """One line per category, budgeted first then alphabetical."""
    lines = [_line(cat, budgets_by_cat[cat.id], sums) for cat in cats]
    # Budgeted first (False sorts before True), then alphabetical.
    lines.sort(key=lambda line: (line.budgeted_minor is None, line.category_name))
    return lines


def _line(cat: Category, budgeted: int | None, sums: CategorySums) -> CategoryBudgetLine:
    spent = sums.spent_this.get(cat.id, 0)
    return CategoryBudgetLine(
        category_id=cat.id,
        category_name=cat.name,
        category_direction=cat.direction,
        category_color=cat.color,
        budgeted_minor=budgeted,
        spent_minor=spent,
        remaining_minor=(budgeted - spent) if budgeted is not None else None,
        avg_monthly_overall_minor=mean_minor(
            sums.overall_sum.get(cat.id, 0), sums.overall_months.get(cat.id, 0)
        ),
        avg_this_year_minor=mean_minor(sums.year_sums.get(cat.id, 0), sums.elapsed_in_year),
        delta_vs_prev_month_minor=spent - sums.spent_prev.get(cat.id, 0),
    )


__all__ = ["CategoryBudgetLine", "CategorySums", "build_budget_lines"]
