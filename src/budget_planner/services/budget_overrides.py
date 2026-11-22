"""Budget default and override entry points for the web layer (T-Q241, ADR-0142).

Routers never import ``repositories``; they call these names. The bindings are plain
pass-throughs: validation, audit and soft-delete stay in ``repositories.budgets``.
"""

from __future__ import annotations

from budget_planner.repositories import budgets as budgets_repo

get_default = budgets_repo.get_default
list_defaults = budgets_repo.list_defaults
set_default = budgets_repo.set_default
set_recurring = budgets_repo.set_recurring
set_one_off = budgets_repo.set_one_off

__all__ = [
    "get_default",
    "list_defaults",
    "set_default",
    "set_one_off",
    "set_recurring",
]
