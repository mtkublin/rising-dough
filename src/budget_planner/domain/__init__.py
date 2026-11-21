"""Domain layer — frozen dataclasses, enums, and money helpers.

All DTOs are immutable (frozen, slots, kw_only). Rows and DTOs mirror the
columns created by `migrations/0002_core_schema.sql`.
"""

from __future__ import annotations

from budget_planner.domain.accounts import (
    Account,
    AccountStats,
    NewAccount,
    PatchAccount,
)
from budget_planner.domain.audit import AuditEntry
from budget_planner.domain.budgets import (
    BudgetDefault,
    BudgetOneOffOverride,
    BudgetRecurringOverride,
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import (
    Category,
    NewCategory,
    PatchCategory,
)
from budget_planner.domain.enums import (
    AuditOperation,
    Cadence,
    Direction,
    OverrideState,
)
from budget_planner.domain.fx import FxRate, NewFxRate
from budget_planner.domain.money import (
    currency_decimals,
    format_money,
    minor_to_major,
    to_minor_units,
)
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedFilter,
    PlannedTransaction,
)
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    Occurrence,
    PatchRecurringRule,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.domain.snapshots import AccountSnapshot, NewAccountSnapshot
from budget_planner.domain.system_categories import (
    RECONCILIATION_CATEGORY_NAME,
    SYSTEM_CATEGORY_NAMES,
    TRANSIT_CATEGORY_NAME,
)
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    Transaction,
    TransactionFilter,
)

__all__ = [
    "RECONCILIATION_CATEGORY_NAME",
    "SYSTEM_CATEGORY_NAMES",
    "TRANSIT_CATEGORY_NAME",
    "Account",
    "AccountSnapshot",
    "AccountStats",
    "AuditEntry",
    "AuditOperation",
    "BudgetDefault",
    "BudgetOneOffOverride",
    "BudgetRecurringOverride",
    "Cadence",
    "Category",
    "Direction",
    "FxRate",
    "NewAccount",
    "NewAccountSnapshot",
    "NewBudgetDefault",
    "NewBudgetOneOffOverride",
    "NewBudgetRecurringOverride",
    "NewCategory",
    "NewFxRate",
    "NewPlannedTransaction",
    "NewRecurringOverride",
    "NewRecurringRule",
    "NewTransaction",
    "Occurrence",
    "OverrideState",
    "PatchAccount",
    "PatchCategory",
    "PatchPlannedTransaction",
    "PatchRecurringRule",
    "PatchTransaction",
    "PlannedFilter",
    "PlannedTransaction",
    "RecurringOverride",
    "RecurringRule",
    "Transaction",
    "TransactionFilter",
    "currency_decimals",
    "format_money",
    "minor_to_major",
    "to_minor_units",
]
