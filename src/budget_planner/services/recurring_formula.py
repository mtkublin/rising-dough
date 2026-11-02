"""Formula-derived recurring amount (ADR-0047; supersedes ADR-0045 §Decision).

Pure parsing + validation helpers plus DB-backed compute primitives. Isolated
from the pure cadence generator so ``generate_occurrences`` / ``apply_overrides``
remain DB-free.

The three private primitives (``_sum_category_in_month``, ``_apply_coefficient``,
``_collect_referenced_category_ids``) are the leaf operators of any future tier
B (nested AST) or tier C (text DSL) evaluator. The top-level evaluator
``compute_formula_amount`` iterates linear-combination terms today; swapping
it for a tree walker leaves the primitives untouched.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from budget_planner.domain.recurring import (
    FORMULA_SCHEMA_VERSION,
    AmountFormula,
    FormulaTerm,
    Occurrence,
    RecurringOverride,
    RecurringRule,
    TermSign,
)

logger = logging.getLogger(__name__)

# Basis-point ceiling: 10 000% — formula sanity guard, not a product
# limit. Anything above this is almost certainly a data-entry mistake
# (coefficient_bps=120 ≠ 1200 confusion). Floor is 1 bps (0.01%).
_BPS_MIN = 1
_BPS_MAX = 1_000_000
_PERCENT_TO_BPS = Decimal("100")


class FormulaError(ValueError):
    """Raised when a formula fails validation at the save boundary."""


class FormulaCycleError(FormulaError):
    """Raised when a formula would create a dependency cycle (ADR-0047)."""


# ---------------------------------------------------------------------------
# Parsing + building (used by routers + tests)
# ---------------------------------------------------------------------------
def parse_percent_to_bps(percent_str: str) -> int:
    """Convert a decimal percent string ("12", "12.5", "0.075") to int bps.

    Rounds half-up to the nearest basis point. Raises :class:`FormulaError`
    on non-decimal input or out-of-range values. Accepts "," as a decimal
    separator (same policy as ``domain.money.parse_amount_str``).
    """
    normalised = (percent_str or "").strip().replace(",", ".")
    if not normalised:
        raise FormulaError("coefficient is required for formula rules")
    try:
        dec = Decimal(normalised)
    except InvalidOperation as exc:
        raise FormulaError("coefficient must be a decimal number") from exc
    bps_dec = (dec * _PERCENT_TO_BPS).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    bps = int(bps_dec)
    if bps < _BPS_MIN or bps > _BPS_MAX:
        raise FormulaError(
            f"coefficient must be between {_BPS_MIN / 100:.2f}% and {_BPS_MAX / 100:.2f}%"
        )
    return bps


def _parse_sign(raw: str) -> TermSign:
    cleaned = (raw or "+").strip()
    if cleaned not in {"+", "-"}:
        raise FormulaError("term sign must be '+' or '-'")
    return cleaned  # type: ignore[return-value]


def build_term(
    *,
    sign: str,
    coefficient_percent: str,
    source_category_ids: Iterable[int],
) -> FormulaTerm:
    """Validate + build a single :class:`FormulaTerm` from form inputs."""
    parsed_sign = _parse_sign(sign)
    bps = parse_percent_to_bps(coefficient_percent)
    seen: set[int] = set()
    cleaned: list[int] = []
    for raw in source_category_ids:
        cid = int(raw)
        if cid in seen:
            continue
        seen.add(cid)
        cleaned.append(cid)
    if not cleaned:
        raise FormulaError("each term needs at least one source category")
    return FormulaTerm(
        sign=parsed_sign,
        coefficient_bps=bps,
        source_category_ids=tuple(cleaned),
    )


def build_formula(terms: Sequence[FormulaTerm]) -> AmountFormula:
    """Wrap a validated terms list into an :class:`AmountFormula`.

    Non-empty terms list required. Each term must already pass :func:`build_term`.
    """
    if not terms:
        raise FormulaError("formula needs at least one term")
    return AmountFormula(terms=tuple(terms), schema_version=FORMULA_SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# Pure compute primitives (future tier B / C leaf operators)
# ---------------------------------------------------------------------------
def _month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    if month == 12:  # noqa: PLR2004
        last = dt.date(year, 12, 31)
    else:
        last = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    return first, last


def _apply_coefficient(sum_minor: int, coefficient_bps: int) -> int:
    """Return ``round_half_up(sum_minor * coefficient_bps / 10 000)`` as int."""
    dec = Decimal(sum_minor) * Decimal(coefficient_bps) / Decimal(10_000)
    return int(dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _collect_referenced_category_ids(formula: AmountFormula) -> set[int]:
    """Flat set of every category id referenced across the formula's terms."""
    out: set[int] = set()
    for term in formula.terms:
        out.update(term.source_category_ids)
    return out


def _sum_category_in_month(
    conn: sqlite3.Connection,
    category_ids: Iterable[int],
    year: int,
    month: int,
    *,
    exclude_rule_id: int | None,
    in_progress: frozenset[int],
    cache: dict[tuple[int, int, int], int],
) -> int:
    """Sum monthly occurrence amounts across rules in ``category_ids``.

    Recurses into formula source rules (chaining per ADR-0047). ``in_progress``
    tracks the current ancestor chain for runtime cycle protection; ``cache``
    memoises child-rule results keyed by ``(rule_id, year, month)`` so diamond
    deps compute once.

    Fixed source rules go through :func:`services.recurring.expand` with
    ``list_overrides_all`` (ADR-0046 soft-consume contract — historical
    overrides stay visible).
    """
    from budget_planner.repositories import recurring as recurring_repo  # noqa: PLC0415
    from budget_planner.services.recurring import expand, generate_occurrences  # noqa: PLC0415

    start, end = _month_bounds(year, month)
    cat_set = set(category_ids)
    total = 0
    for rule in recurring_repo.list_rules(conn, active_only=True):
        if rule.id == exclude_rule_id:
            continue
        if rule.category_id not in cat_set:
            continue
        if rule.id in in_progress:
            raise FormulaCycleError(
                f"formula cycle detected via rule {rule.id} (ancestors: {sorted(in_progress)})"
            )
        key = (rule.id, year, month)
        if key in cache:
            total += cache[key]
            continue
        if rule.amount_formula is None:
            overrides = recurring_repo.list_overrides_all(conn, rule.id)
            value = sum(occ.amount for occ in expand(rule, overrides, start, end))
        else:
            # ADR-0047 month-scope fix: a formula source rule contributes only
            # if its canonical schedule produces an occurrence in (year, month).
            # Without this gate a yearly bonus formula would feed its computed
            # value into every month's parent sum, not just the payout month.
            n_occurrences = len(generate_occurrences(rule, start, end))
            if n_occurrences == 0:
                value = 0
            else:
                per_occurrence = _evaluate(
                    conn,
                    rule.amount_formula,
                    year,
                    month,
                    exclude_rule_id=rule.id,
                    in_progress=in_progress | {rule.id},
                    cache=cache,
                )
                value = n_occurrences * per_occurrence
        cache[key] = value
        total += value
    return total


def _evaluate(
    conn: sqlite3.Connection,
    formula: AmountFormula,
    year: int,
    month: int,
    *,
    exclude_rule_id: int | None,
    in_progress: frozenset[int],
    cache: dict[tuple[int, int, int], int],
) -> int:
    """Evaluate the linear-combination formula for ``(year, month)``.

    Each term contributes ``sign * coefficient * Σ sources``. Memoisation +
    in-progress tracking passed through to ``_sum_category_in_month``.
    """
    total = 0
    for term in formula.terms:
        term_sum = _sum_category_in_month(
            conn,
            term.source_category_ids,
            year,
            month,
            exclude_rule_id=exclude_rule_id,
            in_progress=in_progress,
            cache=cache,
        )
        magnitude = _apply_coefficient(term_sum, term.coefficient_bps)
        total += magnitude if term.sign == "+" else -magnitude
    return total


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_formula_amount(
    conn: sqlite3.Connection,
    formula: AmountFormula,
    year: int,
    month: int,
    *,
    exclude_rule_id: int | None = None,
) -> int:
    """Return the computed amount (minor units) for ``formula`` in ``(year, month)``.

    Thin wrapper that establishes a fresh memoisation cache + empty
    in-progress set. The recursive heavy lifting lives in :func:`_evaluate` +
    :func:`_sum_category_in_month`.
    """
    cache: dict[tuple[int, int, int], int] = {}
    in_progress: frozenset[int] = (
        frozenset({exclude_rule_id}) if exclude_rule_id is not None else frozenset()
    )
    return _evaluate(
        conn,
        formula,
        year,
        month,
        exclude_rule_id=exclude_rule_id,
        in_progress=in_progress,
        cache=cache,
    )


def resolve_rule_amount(
    conn: sqlite3.Connection,
    rule: RecurringRule,
    occurrence_date: dt.date,
) -> int:
    """Return the amount to use for an occurrence of ``rule``.

    Fixed rules → ``rule.default_amount``. Formula rules → recomputed from
    the formula using the occurrence's calendar month.
    """
    if rule.amount_formula is None:
        return rule.default_amount
    return compute_formula_amount(
        conn,
        rule.amount_formula,
        occurrence_date.year,
        occurrence_date.month,
        exclude_rule_id=rule.id,
    )


def rt_expand(
    conn: sqlite3.Connection,
    rule: RecurringRule,
    overrides: Iterable[RecurringOverride],
    range_start: dt.date,
    range_end: dt.date,
) -> tuple[Occurrence, ...]:
    """Expand ``rule`` with runtime amounts; chaining-aware (ADR-0047).

    Fixed rules behave like a direct :func:`services.recurring.expand` call.
    Formula rules get per-month computed amounts substituted before overrides
    apply (override amount still wins when present).
    """
    from budget_planner.services.recurring import (  # noqa: PLC0415
        apply_overrides,
        generate_occurrences,
    )

    occs = generate_occurrences(rule, range_start, range_end)
    if rule.amount_formula is not None:
        occs = tuple(_with_formula_amount(conn, rule, occs))
    return apply_overrides(occs, overrides)


def _with_formula_amount(
    conn: sqlite3.Connection,
    rule: RecurringRule,
    occurrences: Sequence[Occurrence],
) -> Iterable[Occurrence]:
    """Yield occurrences with ``amount`` replaced by per-month formula result."""
    assert rule.amount_formula is not None
    month_cache: dict[tuple[int, int], int] = {}
    for occ in occurrences:
        key = (occ.occurrence_date.year, occ.occurrence_date.month)
        if key not in month_cache:
            month_cache[key] = compute_formula_amount(
                conn,
                rule.amount_formula,
                key[0],
                key[1],
                exclude_rule_id=rule.id,
            )
        yield Occurrence(
            rule_id=occ.rule_id,
            occurrence_date=occ.occurrence_date,
            effective_date=occ.effective_date,
            category_id=occ.category_id,
            account_id=occ.account_id,
            dest_account_id=occ.dest_account_id,
            amount=month_cache[key],
            description=occ.description,
            is_overridden=occ.is_overridden,
            is_skipped=occ.is_skipped,
        )


# ---------------------------------------------------------------------------
# Save-boundary validation
# ---------------------------------------------------------------------------
def validate_formula_sources(
    conn: sqlite3.Connection,
    formula: AmountFormula,
    *,
    exclude_rule_id: int | None = None,
) -> None:
    """Topological reachability check — reject cycles (ADR-0047).

    Walks the dependency graph from ``formula``'s referenced categories →
    rules in those categories → their formulas → ... — depth-first, raising
    :class:`FormulaCycleError` if ``exclude_rule_id`` is ever reachable from
    itself. Visited set guards against re-walking shared subgraphs.
    """
    from budget_planner.repositories import recurring as recurring_repo  # noqa: PLC0415

    # Sentinel for brand-new rules (not yet persisted) so the walk still
    # catches a cycle the new rule would introduce once persisted.
    target_id = -1 if exclude_rule_id is None else exclude_rule_id

    all_rules = recurring_repo.list_rules(conn, active_only=True)
    by_category: dict[int, list[RecurringRule]] = {}
    for rule in all_rules:
        by_category.setdefault(rule.category_id, []).append(rule)

    visited: set[int] = set()
    # Seed the stack with every rule reachable from the proposed formula.
    stack: list[int] = []
    for cat_id in _collect_referenced_category_ids(formula):
        for rule in by_category.get(cat_id, []):
            if rule.id == exclude_rule_id:
                # The rule being saved cannot source itself.
                raise FormulaCycleError("a formula cannot reference its own category")
            stack.append(rule.id)

    while stack:
        rid = stack.pop()
        if rid == target_id:
            raise FormulaCycleError(f"formula would create a cycle via rule {rid}")
        if rid in visited:
            continue
        visited.add(rid)
        found: RecurringRule | None = next((r for r in all_rules if r.id == rid), None)
        if found is None or found.amount_formula is None:
            continue
        for cat_id in _collect_referenced_category_ids(found.amount_formula):
            for child in by_category.get(cat_id, []):
                if child.id not in visited:
                    stack.append(child.id)


# ---------------------------------------------------------------------------
# Preview — unsaved formula evaluation for the Add-entry builder (ADR-0056 §4).
# ---------------------------------------------------------------------------
from dataclasses import dataclass  # noqa: E402
from typing import Literal  # noqa: E402

PreviewErrorCode = Literal["cycle", "non_positive", "invalid_source", "empty"]


@dataclass(frozen=True, slots=True)
class DraftTerm:
    """Shape mirroring the Jinja form rows the Add-entry builder posts.

    ``source_category_ids`` carries integers; ``sign`` and
    ``coefficient_percent`` stay as strings so :func:`build_term` is still
    the single validation boundary.
    """

    sign: str
    coefficient_percent: str
    source_category_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class PreviewOk:
    amount_minor: int


@dataclass(frozen=True, slots=True)
class PreviewError:
    code: PreviewErrorCode
    message: str
    offending_term_index: int | None


PreviewResult = PreviewOk | PreviewError


def _invalid_source_ids(
    conn: sqlite3.Connection,
    terms: Sequence[DraftTerm],
) -> tuple[int, int] | None:
    """Return (term_index, bad_category_id) when a term points at an
    unknown or soft-deleted category; ``None`` on all-valid input.
    """
    from budget_planner.repositories import categories as categories_repo  # noqa: PLC0415

    live_ids = {c.id for c in categories_repo.list_all(conn)}
    for idx, term in enumerate(terms):
        for cid in term.source_category_ids:
            if cid not in live_ids:
                return idx, cid
    return None


def preview(  # noqa: PLR0911 — flat error-code dispatch, splitting hides shape
    conn: sqlite3.Connection,
    when: dt.date,
    draft_rule_id: int | None,
    terms: Sequence[DraftTerm],
) -> PreviewResult:
    """Return the computed value for a draft term list, or an inline error.

    Idempotent; no DB write. Reuses :func:`build_term`, :func:`build_formula`,
    :func:`validate_formula_sources`, and :func:`compute_formula_amount` so
    the preview path and save path cannot drift. Error codes map to the
    four classes the UI needs to react to:

    - ``empty`` — zero terms.
    - ``invalid_source`` — a term references a non-live category id.
    - ``cycle`` — the formula creates a dependency cycle.
    - ``non_positive`` — the computed value is <= 0 for the preview month.
    """
    if not terms:
        return PreviewError(
            code="empty",
            message="formula needs at least one term",
            offending_term_index=None,
        )

    bad = _invalid_source_ids(conn, terms)
    if bad is not None:
        term_idx, bad_id = bad
        return PreviewError(
            code="invalid_source",
            message=f"unknown or archived source category: {bad_id}",
            offending_term_index=term_idx,
        )

    built: list[FormulaTerm] = []
    for idx, draft in enumerate(terms):
        try:
            built.append(
                build_term(
                    sign=draft.sign,
                    coefficient_percent=draft.coefficient_percent,
                    source_category_ids=draft.source_category_ids,
                )
            )
        except FormulaError as exc:
            return PreviewError(
                code="invalid_source",
                message=str(exc),
                offending_term_index=idx,
            )

    try:
        formula = build_formula(built)
    except FormulaError as exc:
        return PreviewError(
            code="empty",
            message=str(exc),
            offending_term_index=None,
        )

    try:
        validate_formula_sources(conn, formula, exclude_rule_id=draft_rule_id)
    except FormulaCycleError as exc:
        return PreviewError(
            code="cycle",
            message=str(exc),
            offending_term_index=None,
        )

    try:
        amount_minor = compute_formula_amount(
            conn,
            formula,
            when.year,
            when.month,
            exclude_rule_id=draft_rule_id,
        )
    except FormulaCycleError as exc:
        return PreviewError(
            code="cycle",
            message=str(exc),
            offending_term_index=None,
        )

    if amount_minor <= 0:
        return PreviewError(
            code="non_positive",
            message="formula resolved to a non-positive amount",
            offending_term_index=None,
        )
    return PreviewOk(amount_minor=amount_minor)


__all__ = [
    "DraftTerm",
    "FormulaCycleError",
    "FormulaError",
    "PreviewError",
    "PreviewErrorCode",
    "PreviewOk",
    "PreviewResult",
    "build_formula",
    "build_term",
    "compute_formula_amount",
    "parse_percent_to_bps",
    "preview",
    "resolve_rule_amount",
    "rt_expand",
    "validate_formula_sources",
]
