"""Recurring rules + overrides + virtual occurrence shape (ADR-0013 / ADR-0038 / ADR-0047)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Any, Final, Literal

from budget_planner.domain.enums import Cadence, OverrideState

# Sentinel for `PatchRecurringRule.next_due` / `amount_formula` / `end_date`
# so we can distinguish "no change" from "explicitly clear". All three are
# nullable at the storage layer; the sentinel keeps the shape symmetric and
# lets admin flows pass through an unmodified value without re-asserting it.
# `end_date` joined the sentinel group in ADR-0063 so the UI can clear a
# previously-set stop date.
_UNCHANGED: Final[object] = object()

# Current storage schema for `AmountFormula` JSON. Bumped on any
# shape-breaking change; migrations keyed off this value. See ADR-0047.
FORMULA_SCHEMA_VERSION: Final[int] = 2

TermSign = Literal["+", "-"]


@dataclass(frozen=True, slots=True, kw_only=True)
class FormulaTerm:
    """One signed term of a linear-combination formula (ADR-0047).

    Semantics: ``sign * (coefficient_bps / 10_000) * Σ(monthly occurrence
    amounts across source rules whose category_id is in source_category_ids)``.
    ``coefficient_bps`` is always positive; sign lives in `sign`.
    """

    sign: TermSign
    coefficient_bps: int
    source_category_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class AmountFormula:
    """Linear-combination formula spec for a recurring rule's amount (ADR-0047).

    Stored as versioned JSON in `recurring_rules.amount_formula`. The amount
    is `Σ terms`. A future ADR tier B (nested AST) or tier C (text DSL) bumps
    `schema_version` and swaps the shape beneath this wrapper — the wrapper
    + storage + repo layer survive the transition.
    """

    terms: tuple[FormulaTerm, ...]
    schema_version: int = FORMULA_SCHEMA_VERSION


@dataclass(frozen=True, slots=True, kw_only=True)
class RecurringRule:
    """Persisted recurring rule.

    `next_due` is the authoritative "when is the next occurrence" column
    (ADR-0038). Every mutation that could shift it must keep it in sync.
    `last_promoted_date` is informational (nullable; untouched by overrides).
    `amount_formula`, when present, overrides `default_amount` at every
    expand / promote / render site (ADR-0045).
    """

    id: int
    user_id: int
    cadence: Cadence
    start_date: date
    end_date: date | None
    category_id: int
    account_id: int
    dest_account_id: int | None
    default_amount: int
    default_description: str
    day_of_month: int | None
    month_of_year: int | None
    active: bool
    next_due: date
    last_promoted_date: date | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    # ADR-0045 — optional with default so pre-formula callers / tests
    # that construct `RecurringRule` directly keep working.
    amount_formula: AmountFormula | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewRecurringRule:
    """Insertable fields for a new recurring rule.

    `next_due` is intentionally absent: the repository computes it on
    insert from the generator (ADR-0038).
    """

    cadence: Cadence
    start_date: date
    category_id: int
    account_id: int
    default_amount: int
    end_date: date | None = None
    dest_account_id: int | None = None
    default_description: str = ""
    day_of_month: int | None = None
    month_of_year: int | None = None
    active: bool = True
    amount_formula: AmountFormula | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PatchRecurringRule:
    """Partial update DTO.

    `next_due` and `amount_formula` accept an explicit admin override via
    the `_UNCHANGED` sentinel pattern — passing a value writes it (including
    `None` to clear a formula), leaving the default does not touch the
    column.
    """

    cadence: Cadence | None = None
    start_date: date | None = None
    end_date: date | object | None = _UNCHANGED
    category_id: int | None = None
    account_id: int | None = None
    dest_account_id: int | None = None
    default_amount: int | None = None
    default_description: str | None = None
    day_of_month: int | None = None
    month_of_year: int | None = None
    active: bool | None = None
    next_due: date | object = _UNCHANGED
    amount_formula: AmountFormula | object | None = _UNCHANGED

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in {"next_due", "amount_formula", "end_date"}:
                if value is _UNCHANGED:
                    continue
                out[f.name] = value
                continue
            if value is not None:
                out[f.name] = value
        return out


@dataclass(frozen=True, slots=True, kw_only=True)
class RecurringOverride:
    """Persisted sparse override for a single occurrence of a rule.

    `promoted_to_txn_id` is `None` while the override is unconsumed; on
    promotion (ADR-0038 step 6e as amended by ADR-0046) the service stamps
    the id of the `transactions` row that consumed the override instead
    of deleting the row. Historical reads (formula compute, ADR-0045) keep
    seeing the override via `list_overrides_all`.
    """

    id: int
    rule_id: int
    occurrence_date: date
    state: OverrideState
    amount_override: int | None
    description_override: str | None
    date_override: date | None
    created_at: datetime
    promoted_to_txn_id: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewRecurringOverride:
    """Insertable fields for a new sparse override."""

    rule_id: int
    occurrence_date: date
    state: OverrideState
    amount_override: int | None = None
    description_override: str | None = None
    date_override: date | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Occurrence:
    """Virtual (non-persisted) occurrence returned by the Phase 2 generator."""

    rule_id: int
    occurrence_date: date
    effective_date: date
    category_id: int
    account_id: int
    dest_account_id: int | None
    amount: int
    description: str
    is_overridden: bool
    is_skipped: bool
