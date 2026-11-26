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

import dataclasses
import datetime as dt
import logging
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from budget_planner.domain.errors import require_present
from budget_planner.domain.money import round_div
from budget_planner.domain.periods import month_bounds
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    Occurrence,
    RecurringOverride,
    RecurringRule,
)
from budget_planner.domain.recurring_schedule import generate_occurrences
from budget_planner.repositories import categories as categories_repo, recurring as recurring_repo
from budget_planner.services import fx as fx_service
from budget_planner.services.fx import FxConverter
from budget_planner.services.recurring_formula_terms import (
    FORMULA_CYCLE_MARK,
    FormulaCycleError,
    FormulaError,
    build_formula,
    build_term,
    parse_percent_to_bps,
    term_input_rows,
)
from budget_planner.services.recurring_overrides import apply_overrides

logger = logging.getLogger(__name__)

_FULL_BPS = 10_000  # 100% in basis points.


# ---------------------------------------------------------------------------
# Pure compute primitives (future tier B / C leaf operators)
# ---------------------------------------------------------------------------
def _apply_coefficient(sum_minor: int, coefficient_bps: int) -> int:
    """Return ``round_half_even(sum_minor * coefficient_bps / 10 000)`` as int."""
    return round_div(sum_minor * coefficient_bps, _FULL_BPS)


def _collect_referenced_category_ids(formula: AmountFormula) -> set[int]:
    """Flat set of every category id referenced across the formula's terms."""
    out: set[int] = set()
    for term in formula.terms:
        out.update(term.source_category_ids)
    return out


_Memo = Mapping[tuple[int, int, int], int]


@dataclasses.dataclass(frozen=True, slots=True)
class FormulaFx:
    """Cache-only FX context so formula source sums convert across currencies (T-Q215).

    A formula's value is in its own rule's account currency; each source rule's
    monthly value is converted from the source account's currency at the rate
    on the first day of the month. Required everywhere a formula amount is
    computed (T-Q286, ADR-0139 amendment 2026-11-22): there is no same-currency
    fallback, so one rule shows one number on every surface.
    """

    converter: FxConverter
    currency_by_account: Mapping[int, str]

    def currency_of(self, account_id: int) -> str:
        return self.currency_by_account.get(account_id, self.converter.base_currency)


@dataclasses.dataclass(frozen=True, slots=True)
class DatesOnly:
    """Marker for callers that read occurrence dates only (income anchor lookups).

    Formula amounts are not evaluated and read ``0``; use :data:`DATES_ONLY`.
    """


DATES_ONLY = DatesOnly()


def formula_fx(conn: sqlite3.Connection, user_id: int, converter: FxConverter) -> FormulaFx:
    """Build the :class:`FormulaFx` for ``user_id`` over an already-built converter."""
    return FormulaFx(converter, fx_service.currency_by_account(conn, user_id, include_deleted=True))


def formula_fx_for(
    conn: sqlite3.Connection, user_id: int, settings: fx_service.HasBaseCurrency, today: dt.date
) -> FormulaFx:
    """Build the cache-only :class:`FormulaFx` from the settings' base currency (no network)."""
    return formula_fx(conn, user_id, fx_service.converter_for(conn, settings, today))


def _into_target(value: int, account_id: int, fx: FormulaFx, target_ccy: str, on: dt.date) -> int:
    """``value`` (in the source account's currency) in ``target_ccy``."""
    return fx.converter.to_currency(value, fx.currency_of(account_id), target_ccy, on)


def _source_rule_month_value(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    start: dt.date,
    end: dt.date,
    *,
    in_progress: frozenset[int],
    cache: _Memo,
    fx: FormulaFx,
) -> tuple[int, _Memo]:
    """Sum the effective amounts of ``rule``'s occurrences in ``[start, end]``.

    Per ADR-0086 every source rule (fixed or formula) contributes its
    *effective* per-occurrence amount: the computed formula value (or
    ``default_amount`` for fixed rules) replaced by any ``amount_override``;
    ``skipped`` occurrences contribute 0. Overrides come from
    ``list_overrides_all`` so soft-consumed (promoted) overrides stay visible
    (ADR-0046). A formula source whose schedule has no occurrence in the
    month contributes 0 without being evaluated (ADR-0047 month-scope gate).
    """
    occs = generate_occurrences(rule, start, end)
    if not occs:
        return 0, cache
    if rule.amount_formula is not None:
        per_occurrence, cache = _evaluate(
            conn,
            user_id,
            rule.amount_formula,
            start.year,
            start.month,
            exclude_rule_id=rule.id,
            in_progress=in_progress | {rule.id},
            cache=cache,
            fx=fx,
            target_ccy=fx.currency_of(rule.account_id),
        )
        occs = tuple(dataclasses.replace(occ, amount=per_occurrence) for occ in occs)
    overrides = recurring_repo.list_overrides_all(conn, user_id, rule.id)
    return sum(occ.amount for occ in apply_overrides(occs, overrides)), cache


def _sum_category_in_month(
    conn: sqlite3.Connection,
    user_id: int,
    category_ids: Iterable[int],
    year: int,
    month: int,
    *,
    exclude_rule_id: int | None,
    in_progress: frozenset[int],
    cache: _Memo,
    fx: FormulaFx,
    target_ccy: str,
) -> tuple[int, _Memo]:
    """Sum monthly occurrence amounts across rules in ``category_ids``.

    Recurses into formula source rules (chaining per ADR-0047). ``in_progress``
    tracks the current ancestor chain for runtime cycle protection; ``cache``
    memoises child-rule results (an immutable mapping, threaded through and
    returned, never mutated) keyed by ``(rule_id, year, month)`` so diamond
    deps compute once.

    Fixed source rules go through :func:`services.recurring.expand` with
    ``list_overrides_all`` (ADR-0046 soft-consume contract — historical
    overrides stay visible).
    """
    start, end = month_bounds(year, month)
    cat_set = set(category_ids)
    total = 0
    for rule in recurring_repo.list_rules(conn, user_id, active_only=True):
        if rule.id == exclude_rule_id:
            continue
        if rule.category_id not in cat_set:
            continue
        if rule.id in in_progress:
            raise FormulaCycleError(
                f"formula cycle detected via rule {rule.id} (ancestors: {sorted(in_progress)})"
            )
        key = (rule.id, year, month)
        if key not in cache:
            value, cache = _source_rule_month_value(
                conn, user_id, rule, start, end, in_progress=in_progress, cache=cache, fx=fx
            )
            cache = {**cache, key: value}
        total += _into_target(cache[key], rule.account_id, fx, target_ccy, start)
    return total, cache


def _evaluate(
    conn: sqlite3.Connection,
    user_id: int,
    formula: AmountFormula,
    year: int,
    month: int,
    *,
    exclude_rule_id: int | None,
    in_progress: frozenset[int],
    cache: _Memo,
    fx: FormulaFx,
    target_ccy: str,
) -> tuple[int, _Memo]:
    """Evaluate the linear-combination formula for ``(year, month)``."""
    total = 0
    for term in formula.terms:
        term_sum, cache = _sum_category_in_month(
            conn,
            user_id,
            term.source_category_ids,
            year,
            month,
            exclude_rule_id=exclude_rule_id,
            in_progress=in_progress,
            cache=cache,
            fx=fx,
            target_ccy=target_ccy,
        )
        magnitude = _apply_coefficient(term_sum, term.coefficient_bps)
        total += magnitude if term.sign == "+" else -magnitude
    return total, cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_formula_amount(
    conn: sqlite3.Connection,
    user_id: int,
    formula: AmountFormula,
    year: int,
    month: int,
    *,
    fx: FormulaFx,
    target_ccy: str,
    exclude_rule_id: int | None = None,
) -> int:
    """Return the computed amount (minor units) for ``formula`` in ``(year, month)``.

    Every source rule is converted into ``target_ccy`` (the owning rule's account
    currency) through ``fx`` before summing (T-Q215, T-Q286); a missing cached
    rate raises :class:`FxUnavailableError`.
    """
    in_progress: frozenset[int] = (
        frozenset({exclude_rule_id}) if exclude_rule_id is not None else frozenset()
    )
    total, _ = _evaluate(
        conn,
        user_id,
        formula,
        year,
        month,
        exclude_rule_id=exclude_rule_id,
        in_progress=in_progress,
        cache={},
        fx=fx,
        target_ccy=target_ccy,
    )
    return total


def resolve_rule_amount(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    occurrence_date: dt.date,
    fx: FormulaFx,
) -> int:
    """Return the amount to use for an occurrence of ``rule``.

    ``fx`` converts formula sources into the rule's account currency (T-Q215, T-Q286).
    """
    if rule.amount_formula is None:
        return rule.default_amount
    return compute_formula_amount(
        conn,
        user_id,
        rule.amount_formula,
        occurrence_date.year,
        occurrence_date.month,
        exclude_rule_id=rule.id,
        fx=fx,
        target_ccy=fx.currency_of(rule.account_id),
    )


def rt_expand(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    rule: RecurringRule,
    overrides: Iterable[RecurringOverride],
    range_start: dt.date,
    range_end: dt.date,
    fx: FormulaFx | DatesOnly,
) -> tuple[Occurrence, ...]:
    """Expand ``rule`` with runtime amounts; chaining-aware (ADR-0047).

    Fixed rules behave like a direct :func:`services.recurring.expand` call.
    Formula rules get per-month computed amounts substituted before overrides
    apply (override amount still wins when present).
    """
    occs = generate_occurrences(rule, range_start, range_end)
    if rule.amount_formula is not None:
        try:
            occs = tuple(_with_formula_amount(conn, user_id, rule, occs, fx))
        except FormulaCycleError:
            # A rule saved before create-time cycle checks: keep its dates, drop its amount,
            # mark it, and keep the page that lists it alive.
            logger.warning("formula cycle in recurring rule %s: amount skipped", rule.id)
            occs = tuple(
                dataclasses.replace(occ, amount=0, description=cycle_label(occ.description))
                for occ in occs
            )
    return apply_overrides(occs, overrides)


def live_rule_amount(
    conn: sqlite3.Connection, user_id: int, rule: RecurringRule, on: dt.date, fx: FormulaFx
) -> tuple[int, bool]:
    """What the rule posts on ``on`` and whether it is a stored formula cycle (Q25, ADR-0047).

    A cyclic stored formula posts 0 and is flagged, exactly like :func:`rt_expand`; the saved
    snapshot is never shown for it.
    """
    try:
        return resolve_rule_amount(conn, user_id, rule, on, fx=fx), False
    except FormulaCycleError:
        return 0, True


def cycle_label(description: str) -> str:
    """The occurrence's description with the "formula cycle" marker (Today shows it)."""
    if not description:
        return FORMULA_CYCLE_MARK
    return f"{description} \N{MIDDLE DOT} {FORMULA_CYCLE_MARK}"


def _with_formula_amount(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    occurrences: Sequence[Occurrence],
    fx: FormulaFx | DatesOnly,
) -> Iterable[Occurrence]:
    """Yield occurrences with ``amount`` replaced by per-month formula result."""
    formula = require_present(rule.amount_formula, "formula of a formula rule")
    month_cache: dict[tuple[int, int], int] = {}
    for occ in occurrences:
        key = (occ.occurrence_date.year, occ.occurrence_date.month)
        if key not in month_cache:
            month_cache[key] = (
                0
                if isinstance(fx, DatesOnly)
                else compute_formula_amount(
                    conn,
                    user_id,
                    formula,
                    key[0],
                    key[1],
                    fx=fx,
                    target_ccy=fx.currency_of(rule.account_id),
                    exclude_rule_id=rule.id,
                )
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
    user_id: int,
    formula: AmountFormula,
    *,
    exclude_rule_id: int | None = None,
    posting_category_id: int | None = None,
) -> None:
    """Topological reachability check — reject cycles (ADR-0047).

    ``posting_category_id`` is the category the drafted rule posts to. A new rule has no id
    yet, so its cycles are found through that category: a source that is the rule's own
    category, or a source rule whose formula (directly or through more rules) reads it.
    """
    # Sentinel for brand-new rules (not yet persisted) so the walk still
    # catches a cycle the new rule would introduce once persisted.
    target_id = -1 if exclude_rule_id is None else exclude_rule_id

    all_rules = recurring_repo.list_rules(conn, user_id, active_only=True)
    by_category: dict[int, list[RecurringRule]] = {}
    for rule in all_rules:
        by_category.setdefault(rule.category_id, []).append(rule)

    stack = _seed_cycle_stack(formula, by_category, exclude_rule_id, posting_category_id)
    _walk_for_cycle(stack, all_rules, by_category, target_id, posting_category_id)


def _seed_cycle_stack(
    formula: AmountFormula,
    by_category: Mapping[int, Sequence[RecurringRule]],
    exclude_rule_id: int | None,
    posting_category_id: int | None,
) -> list[int]:
    """Every rule id reachable from the proposed formula (stack seed)."""
    referenced = _collect_referenced_category_ids(formula)
    if posting_category_id is not None and posting_category_id in referenced:
        raise FormulaCycleError("a formula cannot reference its own category")
    stack: list[int] = []
    for cat_id in referenced:
        for rule in by_category.get(cat_id, []):
            if rule.id == exclude_rule_id:
                # The rule being saved cannot source itself.
                raise FormulaCycleError("a formula cannot reference its own category")
            stack.append(rule.id)
    return stack


def _walk_for_cycle(
    seeds: Sequence[int],
    all_rules: Sequence[RecurringRule],
    by_category: Mapping[int, Sequence[RecurringRule]],
    target_id: int,
    own_category_id: int | None = None,
) -> None:
    """Depth-first walk from ``seeds``; raise when ``target_id`` or ``own_category_id`` is read."""
    by_id = {r.id: r for r in all_rules}
    visited: set[int] = set()
    pending = list(seeds)
    while pending:
        rid = pending.pop()
        referenced = _sources_of(by_id.get(rid))
        if rid == target_id or own_category_id in referenced:
            raise FormulaCycleError(f"formula would create a cycle via rule {rid}")
        if rid in visited:
            continue
        visited.add(rid)
        for cat_id in referenced:
            pending.extend(c.id for c in by_category.get(cat_id, []) if c.id not in visited)


def _sources_of(rule: RecurringRule | None) -> set[int]:
    """Category ids a rule's formula reads (none for a fixed or unknown rule)."""
    if rule is None or rule.amount_formula is None:
        return set()
    return _collect_referenced_category_ids(rule.amount_formula)


# ---------------------------------------------------------------------------
# Preview — unsaved formula evaluation for the Add-entry builder (ADR-0056 §4).
# ---------------------------------------------------------------------------
PreviewErrorCode = Literal["cycle", "non_positive", "invalid_source", "empty"]


def invalid_source_ids(
    conn: sqlite3.Connection,
    user_id: int,
    source_groups: Sequence[Sequence[int]],
) -> tuple[int, int] | None:
    """Return (group_index, bad_category_id) for the first source id that is not
    a live category of ``user_id`` (foreign, unknown or soft-deleted); ``None``
    on all-valid input (Q-028: the save path shares this with the preview).
    """
    live_ids = {c.id for c in categories_repo.list_all(conn, user_id)}
    for idx, group in enumerate(source_groups):
        for cid in group:
            if cid not in live_ids:
                return idx, cid
    return None


def evaluation_month(start: dt.date | None, today: dt.date) -> dt.date:
    """The day whose month a new rule's snapshot and preview are computed for.

    A rule that starts in a later month first posts then, so its sources are read in that month;
    a started (or undated) rule reads the current month.
    """
    return start if start is not None and start > today else today


NO_SOURCE_AMOUNTS = (
    "the picked categories have no recurring amounts in {month}: a formula reads recurring rules"
)


def _no_sources_message(
    conn: sqlite3.Connection,
    user_id: int,
    formula: AmountFormula,
    when: dt.date,
    *,
    fx: FormulaFx,
    target_ccy: str,
    exclude_rule_id: int | None,
) -> str:
    """Why ``formula`` is not positive in ``when``'s month: empty sources, or terms that cancel."""
    in_progress: frozenset[int] = (
        frozenset({exclude_rule_id}) if exclude_rule_id is not None else frozenset()
    )
    cache: _Memo = {}
    for term in formula.terms:
        total, cache = _sum_category_in_month(
            conn,
            user_id,
            term.source_category_ids,
            when.year,
            when.month,
            exclude_rule_id=exclude_rule_id,
            in_progress=in_progress,
            cache=cache,
            fx=fx,
            target_ccy=target_ccy,
        )
        if total != 0:
            return "formula resolved to a non-positive amount"
    return NO_SOURCE_AMOUNTS.format(month=when.strftime("%B %Y"))


def compute_savable_amount(
    conn: sqlite3.Connection,
    user_id: int,
    formula: AmountFormula,
    year: int,
    month: int,
    *,
    fx: FormulaFx,
    target_ccy: str,
    exclude_rule_id: int | None = None,
    posting_category_id: int | None = None,
) -> int:
    """Validate a formula for saving and return its snapshot amount (minor units).

    Rejects (``FormulaError``) a source category that is not the caller's, a
    cycle, and a formula resolving to a non-positive amount (Q-028).
    """
    bad = invalid_source_ids(conn, user_id, [t.source_category_ids for t in formula.terms])
    if bad is not None:
        raise FormulaError(f"unknown or archived source category: {bad[1]}")
    validate_formula_sources(
        conn,
        user_id,
        formula,
        exclude_rule_id=exclude_rule_id,
        posting_category_id=posting_category_id,
    )
    amount = compute_formula_amount(
        conn,
        user_id,
        formula,
        year,
        month,
        fx=fx,
        target_ccy=target_ccy,
        exclude_rule_id=exclude_rule_id,
    )
    if amount <= 0:
        raise FormulaError(
            _no_sources_message(
                conn,
                user_id,
                formula,
                dt.date(year, month, 1),
                fx=fx,
                target_ccy=target_ccy,
                exclude_rule_id=exclude_rule_id,
            )
        )
    return amount


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


def preview_is_quiet(result: PreviewResult) -> bool:
    """True when ``result`` is an empty or incomplete draft (no percent or category yet).

    A quiet result has no line of its own in the formula body; the hero note says why. Every
    other failure (a stale source, a cycle, nothing to read) shows once, in the formula body.
    """
    if isinstance(result, PreviewOk):
        return False
    if result.code == "empty":
        return True
    return result.code == "invalid_source" and not result.message.startswith("unknown or archived")


def preview(
    conn: sqlite3.Connection,
    user_id: int,
    when: dt.date,
    draft_rule_id: int | None,
    terms: Sequence[DraftTerm],
    *,
    fx: FormulaFx,
    target_ccy: str,
    posting_category_id: int | None = None,
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
        return _preview_error("empty", "formula needs at least one term")
    bad = invalid_source_ids(conn, user_id, [t.source_category_ids for t in terms])
    if bad is not None:
        term_idx, bad_id = bad
        return _preview_error(
            "invalid_source", f"unknown or archived source category: {bad_id}", term_idx
        )
    formula = _build_draft_formula(terms)
    if isinstance(formula, PreviewError):
        return formula
    return _evaluate_draft(
        conn,
        user_id,
        formula,
        when,
        draft_rule_id,
        fx=fx,
        target_ccy=target_ccy,
        posting_category_id=posting_category_id,
    )


def _preview_error(
    code: PreviewErrorCode, message: str, offending_term_index: int | None = None
) -> PreviewError:
    return PreviewError(code=code, message=message, offending_term_index=offending_term_index)


def _evaluate_draft(
    conn: sqlite3.Connection,
    user_id: int,
    formula: AmountFormula,
    when: dt.date,
    draft_rule_id: int | None,
    *,
    fx: FormulaFx,
    target_ccy: str,
    posting_category_id: int | None,
) -> PreviewResult:
    """Cycle-check the draft, compute it for ``when`` and require a positive value."""
    try:
        validate_formula_sources(
            conn,
            user_id,
            formula,
            exclude_rule_id=draft_rule_id,
            posting_category_id=posting_category_id,
        )
        amount_minor = compute_formula_amount(
            conn,
            user_id,
            formula,
            when.year,
            when.month,
            fx=fx,
            target_ccy=target_ccy,
            exclude_rule_id=draft_rule_id,
        )
    except FormulaCycleError as exc:
        return _preview_error("cycle", str(exc))
    if amount_minor <= 0:
        return _preview_error(
            "non_positive",
            _no_sources_message(
                conn,
                user_id,
                formula,
                when,
                fx=fx,
                target_ccy=target_ccy,
                exclude_rule_id=draft_rule_id,
            ),
        )
    return PreviewOk(amount_minor=amount_minor)


def _build_draft_formula(terms: Sequence[DraftTerm]) -> AmountFormula | PreviewError:
    """Build the formula from draft terms, mapping build errors to preview errors."""
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
            return _preview_error("invalid_source", str(exc), idx)
    try:
        return build_formula(built)
    except FormulaError as exc:
        return _preview_error("empty", str(exc))


__all__ = [
    "DATES_ONLY",
    "FORMULA_CYCLE_MARK",
    "DatesOnly",
    "DraftTerm",
    "FormulaCycleError",
    "FormulaError",
    "FormulaFx",
    "PreviewError",
    "PreviewErrorCode",
    "PreviewOk",
    "PreviewResult",
    "build_formula",
    "build_term",
    "compute_formula_amount",
    "compute_savable_amount",
    "cycle_label",
    "evaluation_month",
    "formula_fx",
    "formula_fx_for",
    "invalid_source_ids",
    "live_rule_amount",
    "parse_percent_to_bps",
    "preview",
    "preview_is_quiet",
    "resolve_rule_amount",
    "rt_expand",
    "term_input_rows",
    "validate_formula_sources",
]
