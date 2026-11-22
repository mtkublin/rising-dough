"""Recurring rule form parsing and validation (T-Q266): moved out of the recurring router.

Request parsing plus the service lookups a form needs to report per-field errors. No rendering.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from datetime import date
from types import MappingProxyType

from starlette.datastructures import FormData

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import AmountFormula
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    recurring_formula as formula_svc,
)
from budget_planner.web.params import parse_int, positive_amount

TermInput = dict[str, object]

EMPTY_TERM_INPUT: Mapping[str, object] = MappingProxyType(
    {
        "sign": "+",
        "coefficient_percent": "",
        "source_category_ids": (),
    }
)

_TERM_FIELD_RE = re.compile(r"^terms\[(\d+)\]\[(sign|coefficient_percent|source_category_ids)\]$")
_CADENCES: Mapping[str, Cadence] = MappingProxyType({c.value: c for c in Cadence})
_DEST = "dest_account_id"


def formula_source_candidates(conn: sqlite3.Connection, user_id: int) -> list[Category]:
    """Return categories eligible as formula sources (user-visible income+expense)."""
    return [
        c
        for c in categories_service.list_all(conn, user_id)
        if c.direction in (Direction.INCOME, Direction.EXPENSE)
    ]


def parse_terms_from_form(form: FormData) -> list[TermInput]:
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
    for key, raw in form.multi_items():
        m = _TERM_FIELD_RE.match(key)
        if m is None:
            continue
        idx = int(m.group(1))
        field = m.group(2)
        ids.setdefault(idx, [])
        if field == "source_category_ids":
            ids[idx].append(str(raw))
        elif field == "sign":
            signs[idx] = str(raw)
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


def parse_draft_terms(form: FormData) -> list[formula_svc.DraftTerm] | None:
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


def _resolve_formula(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    term_inputs: list[TermInput],
    exclude_rule_id: int | None,
    today: date,
) -> tuple[int | None, AmountFormula | None, dict[str, str]]:
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
            conn, user_id, formula, today.year, today.month, exclude_rule_id=exclude_rule_id
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
) -> tuple[int | None, AmountFormula | None, dict[str, str]]:
    """Validate fixed-vs-formula branch; return (default_amount_minor, formula, errors)."""
    is_formula = amount_source == "formula"
    if account_currency is None:
        field = "amount_source" if is_formula else "default_amount"
        return None, None, {field: "unknown account currency"}
    if is_formula:
        return _resolve_formula(
            conn, user_id, term_inputs=term_inputs, exclude_rule_id=exclude_rule_id, today=today
        )
    minor, amount_err = positive_amount(default_amount, account_currency)
    return minor, None, ({} if amount_err is None else {"default_amount": amount_err})
