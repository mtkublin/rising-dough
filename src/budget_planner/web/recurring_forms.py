"""Recurring rule form parsing and validation (T-Q266): moved out of the recurring router.

Request parsing plus the service lookups a form needs to report per-field errors. No rendering.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any

from starlette.datastructures import FormData, QueryParams

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.money import ascii_minus
from budget_planner.domain.recurring import (
    AmountFormula,
    NewRecurringRule,
    PatchRecurringRule,
    RecurringRule,
    day_of_month_error,
    end_date_error,
)
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    recurring as recurring_svc,
    recurring_formula as formula_svc,
)
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web.budget_forms import OVERRIDE_YEARS
from budget_planner.web.params import parse_date, parse_int, positive_amount

TermInput = dict[str, object]

EMPTY_TERM_INPUT: Mapping[str, object] = MappingProxyType(
    {
        "sign": "+",
        "coefficient_percent": "",
        "source_category_ids": (),
    }
)

# The old shell's form posts terms[i][sign|coefficient_percent|source_category_ids]. The dialog's
# formula fragment posts the handoff names (the vendored formula.js re-indexes only those):
# components[i][sign|percent|categories], U+2212 for a subtracted component.
_TERM_FIELD_RE = re.compile(r"^terms\[(\d+)\]\[(sign|coefficient_percent|source_category_ids)\]$")
_COMPONENT_FIELD_RE = re.compile(r"^components\[(\d+)\]\[(sign|percent|categories)\]$")
_COMPONENT_FIELDS = MappingProxyType(
    {"sign": "sign", "percent": "coefficient_percent", "categories": "source_category_ids"}
)
_COMPONENTS_PREFIX = "components["


def category_alias(category_id: str, category: str) -> str:
    """The posted category: ``category_id`` wins over the picker's ``category`` when both come.

    The one place the two spellings meet (the dialog's picker posts ``category``, the old form
    ``category_id``); the transaction, planned and recurring creates all read it through here.
    """
    return category_id or category


_CADENCES: Mapping[str, Cadence] = MappingProxyType({c.value: c for c in Cadence})
_DEST = "dest_account_id"


def formula_source_candidates(conn: sqlite3.Connection, user_id: int) -> list[Category]:
    """Return categories eligible as formula sources (user-visible income+expense)."""
    return [
        c
        for c in categories_service.list_all(conn, user_id)
        if c.direction in (Direction.INCOME, Direction.EXPENSE)
    ]


def parse_terms_from_form(form: FormData | QueryParams) -> list[TermInput]:
    """Group `terms[i][field]` form entries into a dense indexed list.

    Returns a list of ``{"sign", "coefficient_percent", "source_category_ids"}``
    dicts in ascending index order. Holes (removed row 1 in a form that
    posted rows 0 and 2) collapse to a contiguous list. Values are left as
    strings / tuples so :func:`formula_svc.build_term` is the single
    validation boundary.
    """
    signs: dict[int, str] = {}
    percents: dict[int, str] = {}
    ids: dict[int, list[str]] = {}
    items = list(form.multi_items())
    # Never merge the two spellings: any ``components[`` key makes the post a dialog post.
    dialog = any(key.startswith(_COMPONENTS_PREFIX) for key, _ in items)
    pattern = _COMPONENT_FIELD_RE if dialog else _TERM_FIELD_RE
    for key, raw in items:
        m = pattern.match(key)
        if m is None:
            continue
        idx = int(m.group(1))
        field = _COMPONENT_FIELDS[m.group(2)] if dialog else m.group(2)
        ids.setdefault(idx, [])
        if field == "source_category_ids":
            ids[idx].append(str(raw))
        elif field == "sign":
            signs[idx] = ascii_minus(str(raw))
        else:
            percents[idx] = str(raw)
    return [
        {
            "sign": signs.get(idx, "+"),
            "coefficient_percent": percents.get(idx, ""),
            "source_category_ids": tuple(ids[idx]),
        }
        for idx in sorted(ids)
    ]


def evaluation_day(form: FormData | QueryParams, today: date) -> date:
    """The day whose month the formula reads: the posted start when it is later, else ``today``.

    One owner for the hero and the live preview (``formula_svc.evaluation_month``, ADR-0047).
    """
    return formula_svc.evaluation_month(parse_date(str(form.get("start_date", ""))), today)


def parse_draft_terms(form: FormData | QueryParams) -> list[formula_svc.DraftTerm] | None:
    """Posted terms as preview drafts; ``None`` when a source category id is not an integer."""
    drafts: list[formula_svc.DraftTerm] = []
    for row in parse_terms_from_form(form):
        raw_ids = row.get("source_category_ids")
        cat_ids = [parse_int(str(v)) for v in raw_ids] if isinstance(raw_ids, tuple) else []
        valid_ids = tuple(c for c in cat_ids if c is not None)
        if len(valid_ids) != len(cat_ids):
            return None
        drafts.append(
            formula_svc.DraftTerm(
                sign=_text(row.get("sign"), "+"),
                coefficient_percent=_text(row.get("coefficient_percent"), ""),
                source_category_ids=valid_ids,
            )
        )
    return drafts


def validate_cadence(value: str) -> Cadence | None:
    return _CADENCES.get(value)


def _transit_pair_error(dest: Account, source: Account | None) -> str | None:
    if source is None:
        return None
    if dest.currency != source.currency:
        return "cross-currency transit not supported"
    if dest.id == source.id:
        return "destination must differ from source"
    return None


def resolve_dest_account(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    dest_account_id_raw: str,
    category: Category | None,
    source_account: Account | None,
) -> tuple[int | None, dict[str, str]]:
    """Validate the destination account input (mirrors transactions router).

    Transits (``direction=transit``) require a destination with matching
    currency; non-transit categories ignore any posted value.
    """
    if category is None or category.direction != Direction.TRANSIT:
        return None, {}
    if not dest_account_id_raw:
        return None, {_DEST: "transit requires destination account"}
    parsed = parse_int(dest_account_id_raw)
    if parsed is None:
        return None, {_DEST: "invalid destination"}
    dest = accounts_service.find_by_id(conn, user_id, parsed)
    if dest is None:
        return None, {_DEST: "unknown destination"}
    if (pair_error := _transit_pair_error(dest, source_account)) is not None:
        return None, {_DEST: pair_error}
    return parsed, {}


def _text(value: object, default: str) -> str:
    return value if isinstance(value, str) else default


def _category_ids(value: object) -> list[int]:
    return [int(str(v)) for v in value] if isinstance(value, list | tuple) else []


PERCENT_REQUIRED = "Enter a percentage, e.g. 19 or 12.5"
CATEGORY_REQUIRED = "Pick at least one category"


def component_error_key(index: int, field: str) -> str:
    """Error key of one formula component field (``percent`` or ``categories``), as posted."""
    return f"components[{index}][{field}]"


def component_errors(term_inputs: list[TermInput]) -> dict[str, str]:
    """Per-component messages of the dialog's formula (handoff: under the failing component).

    A missing percentage and a missing category are reported on their own component, so the
    dialog marks the field and prints the line beneath it; a bad sign or a formula-level failure
    stays the single ``formula`` error.
    """
    errors: dict[str, str] = {}
    for index, term in enumerate(term_inputs):
        percent = _text(term.get("coefficient_percent"), "").strip()
        if not percent:
            errors[component_error_key(index, "percent")] = PERCENT_REQUIRED
        else:
            try:
                formula_svc.parse_percent_to_bps(percent)
            except formula_svc.FormulaError as exc:
                errors[component_error_key(index, "percent")] = str(exc)
        if not _category_ids(term.get("source_category_ids")):
            errors[component_error_key(index, "categories")] = CATEGORY_REQUIRED
    return errors


def _resolve_formula(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    term_inputs: list[TermInput],
    exclude_rule_id: int | None,
    today: date,
    fx: FormulaFx,
    target_ccy: str,
    posting_category_id: int | None,
    start: date | None,
) -> tuple[int | None, AmountFormula | None, dict[str, str]]:
    if component_failures := component_errors(term_inputs):
        return None, None, component_failures
    try:
        terms = [
            formula_svc.build_term(
                sign=_text(t.get("sign"), "+"),
                coefficient_percent=_text(t.get("coefficient_percent"), ""),
                source_category_ids=_category_ids(t.get("source_category_ids")),
            )
            for t in term_inputs
        ]
        formula = formula_svc.build_formula(terms)
        snapshot = formula_svc.compute_savable_amount(
            conn,
            user_id,
            formula,
            (month := formula_svc.evaluation_month(start, today)).year,
            month.month,
            fx=fx,
            target_ccy=target_ccy,
            exclude_rule_id=exclude_rule_id,
            posting_category_id=posting_category_id,
        )
    except formula_svc.FormulaError as exc:
        return None, None, {"formula": str(exc)}
    return snapshot, formula, {}


def resolve_amount_inputs(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    amount_source: str,
    default_amount: str,
    term_inputs: list[TermInput],
    account_currency: str | None,
    exclude_rule_id: int | None,
    today: date,
    fx: FormulaFx,
    posting_category_id: int | None = None,
    start: date | None = None,
) -> tuple[int | None, AmountFormula | None, dict[str, str]]:
    """Validate fixed-vs-formula branch; return (default_amount_minor, formula, errors)."""
    is_formula = amount_source == "formula"
    if account_currency is None:
        field = "amount_source" if is_formula else "default_amount"
        return None, None, {field: "unknown account currency"}
    if is_formula:
        return _resolve_formula(
            conn,
            user_id,
            term_inputs=term_inputs,
            exclude_rule_id=exclude_rule_id,
            today=today,
            fx=fx,
            target_ccy=account_currency,
            posting_category_id=posting_category_id,
            start=start,
        )
    minor, amount_err = positive_amount(default_amount, account_currency)
    return minor, None, ({} if amount_err is None else {"default_amount": amount_err})


@dataclass(frozen=True, slots=True)
class RuleFields:
    """Raw posted recurring-rule form text (create and edit share the shape)."""

    cadence: str
    start_date: str
    end_date: str
    category_id: str
    account_id: str
    dest_account_id: str
    default_amount: str
    default_description: str
    day_of_month: str
    amount_source: str
    terms: list[TermInput]

    @property
    def form_terms(self) -> list[TermInput]:
        """Terms to re-render on error: at least one (empty) row."""
        return self.terms or [dict(EMPTY_TERM_INPUT)]


def read_rule_fields(form: FormData) -> RuleFields:
    def text(key: str, default: str = "") -> str:
        return str(form.get(key, default))

    return RuleFields(
        cadence=text("cadence"),
        start_date=text("start_date"),
        end_date=text("end_date"),
        category_id=category_alias(text("category_id"), text("category")),
        account_id=text("account_id"),
        dest_account_id=text("dest_account_id"),
        default_amount=text("default_amount"),
        default_description=text("default_description"),
        day_of_month=text("day_of_month"),
        amount_source=text("amount_source", "fixed"),
        terms=parse_terms_from_form(form),
    )


def parse_rule_ids(fields: RuleFields) -> tuple[int, int] | None:
    """Return ``(category_id, account_id)``, or ``None`` when either is not an integer."""
    category_id = parse_int(fields.category_id)
    account_id = parse_int(fields.account_id)
    if category_id is None or account_id is None:
        return None
    return category_id, account_id


@dataclass(frozen=True, slots=True)
class ValidRule:
    """A rule form that passed validation: every value present."""

    cadence: Cadence
    start: date
    end: date | None
    category_id: int
    account_id: int
    account: Account
    category: Category
    dest_id: int | None
    amount_minor: int
    formula: AmountFormula | None


@dataclass(frozen=True, slots=True)
class RuleDraft:
    """Outcome of validating a rule form: the valid rule, or the per-field errors."""

    valid: ValidRule | None
    errors: dict[str, str]


def _parse_end_date(raw: str, start: date | None) -> tuple[date | None, dict[str, str]]:
    if not raw:
        return None, {}
    end = parse_date(raw)
    if end is None:
        return None, {"end_date": "invalid date"}
    end_err = end_date_error(start, end)
    return end, ({} if end_err is None else {"end_date": end_err})


def _date_errors(
    fields: RuleFields, cadence: Cadence | None, start: date | None, cadence_error: str
) -> tuple[date | None, dict[str, str]]:
    errors: dict[str, str] = {}
    if cadence is None:
        errors["cadence"] = cadence_error
    if start is None:
        errors["start_date"] = "invalid date"
    end, end_errors = _parse_end_date(fields.end_date, start)
    return end, {**errors, **end_errors}


def _lookup_refs(
    conn: sqlite3.Connection, user_id: int, fields: RuleFields, ids: tuple[int, int]
) -> tuple[Account | None, Category | None, int | None, dict[str, str]]:
    category_id, account_id = ids
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    errors: dict[str, str] = {}
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    dest_id, dest_errors = resolve_dest_account(
        conn,
        user_id,
        dest_account_id_raw=fields.dest_account_id,
        category=cat,
        source_account=acc,
    )
    return acc, cat, dest_id, {**errors, **dest_errors}


def parse_day_of_month(raw: str) -> tuple[int | None, dict[str, str]]:
    """Anchor day text to ``(day, {})``; blank is ``(None, {})``, bad is a field error."""
    text = raw.strip()
    if not text:
        return None, {}
    day = parse_int(text, minimum=0)
    bad = day_of_month_error(day if day is not None else 0)
    if day is None or bad is not None:
        return None, {"day_of_month": bad or day_of_month_error(0) or ""}
    return day, {}


def _missing_id_errors(fields: RuleFields) -> dict[str, str]:
    """Per-field messages for a category or account that is blank or not a number."""
    errors: dict[str, str] = {}
    if parse_int(fields.category_id) is None:
        errors["category_id"] = "Pick a category" if not fields.category_id else "unknown category"
    if parse_int(fields.account_id) is None:
        errors["account_id"] = "unknown account"
    return errors


def validate_rule_draft(
    conn: sqlite3.Connection,
    user_id: int,
    fields: RuleFields,
    ids: tuple[int, int] | None,
    *,
    fx: FormulaFx,
    today: date,
    exclude_rule_id: int | None,
    cadence_error: str,
) -> RuleDraft:
    cadence = validate_cadence(fields.cadence)
    start = parse_date(fields.start_date)
    end, errors = _date_errors(fields, cadence, start, cadence_error)
    errors = {**errors, **parse_day_of_month(fields.day_of_month)[1]}
    if ids is None:
        return RuleDraft(None, {**errors, **_missing_id_errors(fields)})
    category_id, account_id = ids
    acc, cat, dest_id, ref_errors = _lookup_refs(conn, user_id, fields, ids)
    errors = {**errors, **ref_errors}
    minor, formula, amount_errors = resolve_amount_inputs(
        conn,
        user_id,
        fx=fx,
        amount_source=fields.amount_source,
        default_amount=fields.default_amount,
        term_inputs=fields.terms,
        account_currency=acc.currency if acc else None,
        exclude_rule_id=exclude_rule_id,
        today=today,
        posting_category_id=category_id,
        start=start,
    )
    errors = {**errors, **amount_errors}
    if errors:
        return RuleDraft(None, errors)
    if cadence is None or start is None or acc is None or cat is None or minor is None:
        return RuleDraft(None, {"form": "invalid"})
    valid = ValidRule(
        cadence, start, end, category_id, account_id, acc, cat, dest_id, minor, formula
    )
    return RuleDraft(valid, {})


def new_rule_from(fields: RuleFields, valid: ValidRule, today: date) -> NewRecurringRule:
    """Build the create command from a valid form."""
    # ADR-0063: a stop date already in the past means the schedule is dead on arrival, so
    # insert it inactive; it never shows up in Upcoming or Forecast before the first promotion.
    initial_active = not (valid.end is not None and valid.end < today)
    return recurring_svc.with_anchor_day(
        NewRecurringRule(
            cadence=valid.cadence,
            start_date=valid.start,
            end_date=valid.end,
            category_id=valid.category_id,
            account_id=valid.account_id,
            dest_account_id=valid.dest_id,
            default_amount=valid.amount_minor,
            default_description=fields.default_description,
            day_of_month=parse_day_of_month(fields.day_of_month)[0],
            amount_formula=valid.formula,
            active=initial_active,
        )
    )


def rule_patch_from(
    fields: RuleFields, valid: ValidRule, rule: RecurringRule
) -> PatchRecurringRule:
    """Build the edit patch from a valid form."""
    patch: dict[str, Any] = {
        "cadence": valid.cadence,
        "start_date": valid.start,
        "category_id": valid.category_id,
        "account_id": valid.account_id,
        "dest_account_id": valid.dest_id,
        "default_amount": valid.amount_minor,
        "default_description": fields.default_description,
        "amount_formula": valid.formula,
        # An empty end date clears it (forms always carry the field).
        "end_date": valid.end,
    }
    # ADR-0063: shortening the stop date past the next pending occurrence deactivates the rule
    # in the same patch, so Upcoming and Forecast stop surfacing it before the next promotion.
    if valid.end is not None and rule.next_due > valid.end:
        patch["active"] = False
    # A blank day keeps the stored one (None in a patch means "unchanged").
    if (day := parse_day_of_month(fields.day_of_month)[0]) is not None:
        patch["day_of_month"] = day
    return PatchRecurringRule(**patch)


_OVERRIDE_MONTHS = range(1, 13)


def year_or(year: int, fallback: int) -> int:
    return year if year in OVERRIDE_YEARS else fallback


def month_or(month: int, fallback: int) -> int:
    return month if month in _OVERRIDE_MONTHS else fallback


@dataclass(frozen=True, slots=True)
class ValidOverride:
    occurrence: date
    amount_minor: int


@dataclass(frozen=True, slots=True)
class OverrideError:
    field: str
    message: str


def check_override(
    rule: RecurringRule, account: Account | None, year: int, month: int, amount: str
) -> ValidOverride | OverrideError:
    if not (year in OVERRIDE_YEARS and month in _OVERRIDE_MONTHS):
        return OverrideError("month", "invalid year or month")
    occ = recurring_svc.occurrence_in_month(rule, year, month)
    if occ is None:
        return OverrideError("month", f"rule has no occurrence in {year:04d}-{month:02d}")
    if account is None:
        return OverrideError("account", "rule has no live account")
    amount_minor, amount_err = positive_amount(amount, account.currency)
    if amount_minor is None:
        return OverrideError("amount", amount_err or "invalid amount")
    return ValidOverride(occ, amount_minor)


@dataclass(frozen=True, slots=True)
class PromoteInput:
    """Parsed promote form: optional edits plus per-field errors."""

    operation_date: date | None
    amount_minor: int | None
    errors: dict[str, str]


def parse_promote_input(operation_date: str, amount: str, account: Account | None) -> PromoteInput:
    errors: dict[str, str] = {}
    op_date = parse_date(operation_date) if operation_date else None
    if operation_date and op_date is None:
        errors["operation_date"] = "invalid date"
    amount_minor: int | None = None
    if amount and account is None:
        errors["amount"] = "unknown account currency"
    elif amount and account is not None:
        amount_minor, amount_err = positive_amount(amount, account.currency)
        if amount_err is not None:
            errors["amount"] = amount_err
    return PromoteInput(op_date, amount_minor, errors)
