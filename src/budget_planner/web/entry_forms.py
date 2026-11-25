"""Form validation for the transaction and planned entry forms (T-Q265).

Turns raw form text into typed values plus a field-keyed error map. Rules live
in services (``transit_shape_error``, ``validate_distinct_accounts``); this
module only sequences them per form and names the result for the router.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType

from starlette.datastructures import FormData, QueryParams

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.errors import require_present
from budget_planner.domain.limits import DESCRIPTION_MAX_LENGTH, length_error
from budget_planner.domain.money import (
    format_figure,
    format_major,
    format_money,
    parse_amount_minor,
    sign_glyph,
)
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedTransaction,
)
from budget_planner.domain.transactions import (
    NewTransaction,
    PatchTransaction,
    Transaction,
    signed_legs,
)
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    limit_preview as limit_preview_service,
    planned as planned_service,
    recurring_formula as formula_svc,
    transactions as transactions_service,
)
from budget_planner.services.account_pair import validate_distinct_accounts
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web.params import parse_date, parse_int, positive_amount
from budget_planner.web.recurring_forms import (
    EMPTY_TERM_INPUT,
    category_alias,
    formula_source_candidates,
    parse_draft_terms,
)


@dataclass(frozen=True, slots=True)
class EntryCheck:
    """Outcome of validating one entry form submission."""

    errors: dict[str, str] = field(default_factory=dict)
    op_date: date | None = None
    minor: int | None = None
    dest_id: int | None = None
    account: Account | None = None
    category: Category | None = None

    def valid_values(self) -> tuple[date, int]:
        """The parsed date and amount of an error-free check (``InvariantError`` otherwise)."""
        return (
            require_present(self.op_date, "validated operation date"),
            require_present(self.minor, "validated amount"),
        )


def _amount(raw: str, acc: Account | None) -> tuple[int | None, dict[str, str]]:
    """Positive amount in the account's currency, with its field error (if any)."""
    if acc is None:
        return None, {}
    minor, err = positive_amount(raw, acc.currency)
    return minor, ({"amount": err} if err else {})


def _shape_error(
    conn: sqlite3.Connection, user_id: int, cat: Category, account_id: int, dest: int | None
) -> str | None:
    return transactions_service.transit_shape_error(
        conn, user_id, direction=cat.direction, account_id=account_id, dest_account_id=dest
    )


def _date_error(raw: str) -> tuple[date | None, dict[str, str]]:
    parsed = parse_date(raw)
    return parsed, ({} if parsed is not None else {"operation_date": "invalid date"})


def _description_error(description: str) -> dict[str, str]:
    too_long = length_error(description, maximum=DESCRIPTION_MAX_LENGTH)
    return {} if too_long is None else {"description": too_long}


def _unknown_errors(acc: Account | None, cat: Category | None) -> dict[str, str]:
    errors: dict[str, str] = {}
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    return errors


def _txn_create_dest(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cat: Category,
    acc: Account | None,
    account_id: int,
    dest_account_id: str,
) -> tuple[int | None, dict[str, str]]:
    """Destination of a new transaction; only transit categories read one."""
    if cat.direction != Direction.TRANSIT:
        return None, {}
    parsed = parse_int(dest_account_id) if dest_account_id else None
    if dest_account_id and parsed is None:
        return None, {"dest_account_id": "invalid destination"}
    if acc is None:
        return None, {}
    shape = _shape_error(conn, user_id, cat, account_id, parsed)
    return (parsed, {}) if shape is None else (None, {"dest_account_id": shape})


def check_txn_create(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    description: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate a new transaction (a destination is read only for transit categories)."""
    op_date, errors = _date_error(operation_date)
    errors.update(_description_error(description))
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    errors.update(_unknown_errors(acc, cat))
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    dest_id: int | None = None
    if cat is not None:
        dest_id, dest_errors = _txn_create_dest(
            conn, user_id, cat=cat, acc=acc, account_id=account_id, dest_account_id=dest_account_id
        )
        errors.update(dest_errors)
    return EntryCheck(errors, op_date, minor, dest_id, acc, cat)


def _txn_update_dest_error(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cat: Category | None,
    acc: Account | None,
    account_id: int,
    submitted_raw: str,
    submitted: int | None,
    effective: int | None,
) -> dict[str, str]:
    if submitted_raw and submitted is None:
        return {"dest_account_id": "invalid destination"}
    if acc is not None and cat is not None:
        shape = _shape_error(conn, user_id, cat, account_id, effective)
        if shape is not None:
            return {"dest_account_id": shape}
    return {}


def check_txn_update(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    existing_dest_id: int | None,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    description: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate an edited transaction; the submitted destination wins over the stored one."""
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    op_date, errors = _date_error(operation_date)
    errors.update(_description_error(description))
    errors.update(_unknown_errors(acc, cat))
    submitted = parse_int(dest_account_id) if dest_account_id else None
    effective = submitted if submitted is not None else existing_dest_id
    errors.update(
        _txn_update_dest_error(
            conn,
            user_id,
            cat=cat,
            acc=acc,
            account_id=account_id,
            submitted_raw=dest_account_id,
            submitted=submitted,
            effective=effective,
        )
    )
    same = validate_distinct_accounts(account_id, effective)
    if same is not None:
        errors["dest_account_id"] = same
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    return EntryCheck(errors, op_date, minor, submitted, acc, cat)


def _planned_dest(
    conn: sqlite3.Connection, user_id: int, account_id: int, dest_account_id: str
) -> tuple[int | None, dict[str, str]]:
    """Destination of a new planned transaction: parsed, existing and distinct from the source."""
    if not dest_account_id.strip():
        return None, {}
    try:
        dest_id = int(dest_account_id)
    except ValueError:
        return None, {"dest_account_id": "invalid dest account"}
    if accounts_service.find_by_id(conn, user_id, dest_id) is None:
        return dest_id, {"dest_account_id": "unknown dest account"}
    same = validate_distinct_accounts(account_id, dest_id)
    return dest_id, ({} if same is None else {"dest_account_id": same})


def check_planned_create(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate a new planned transaction."""
    op_date, errors = _date_error(operation_date)
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    errors.update(_unknown_errors(acc, cat))
    dest_id, dest_errors = _planned_dest(conn, user_id, account_id, dest_account_id)
    errors.update(dest_errors)
    if cat is not None and acc is not None and "dest_account_id" not in errors:
        shape = _shape_error(conn, user_id, cat, account_id, dest_id)
        if shape is not None:
            errors["dest_account_id"] = shape
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    return EntryCheck(errors, op_date, minor, dest_id, acc, cat)


def check_planned_update(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    existing_dest_id: int | None,
    operation_date: str,
    category_id: int,
    account_id: int,
    amount: str,
    dest_account_id: str,
) -> EntryCheck:
    """Validate an edited planned transaction; the submitted destination wins."""
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    op_date, errors = _date_error(operation_date)
    if acc is None:
        errors["account_id"] = "unknown account"
    submitted = int(dest_account_id) if dest_account_id.strip().isdigit() else None
    effective = submitted if submitted is not None else existing_dest_id
    same = validate_distinct_accounts(account_id, effective)
    if same is not None:
        errors["dest_account_id"] = same
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        errors["category_id"] = "unknown category"
    elif acc is not None and same is None:
        shape = _shape_error(conn, user_id, cat, account_id, effective)
        if shape is not None:
            errors["dest_account_id"] = shape
    minor, amount_errors = _amount(amount, acc)
    errors.update(amount_errors)
    return EntryCheck(errors, op_date, minor, submitted, acc, cat)


# ---------------------------------------------------------------------------
# New-entry dialog context (T-UR07b, ADR-0107): one builder for the three tabs.
# ---------------------------------------------------------------------------

ENTRY_TABS: tuple[str, ...] = ("happened", "planned", "repeats")
TAB_ACTIONS = MappingProxyType(
    {"happened": "/transactions", "planned": "/planned", "repeats": "/recurring"}
)


_TRANSIT_GLYPH = (
    "\N{RIGHTWARDS ARROW OVER LEFTWARDS ARROW}"  # the hero sign of a transit (handoff edit)
)


def _direction_sign(direction: Direction) -> str | None:
    """Hero sign of a category by the canonical direction rule; none for transit, adjustment."""
    if direction not in (Direction.EXPENSE, Direction.INCOME):
        return None
    return sign_glyph(signed_legs(direction, 1, 0, None)[0].amount_minor < 0)


def _component_rows(terms: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Posted or stored formula terms in the shape ``fields/formula`` renders."""
    rows: list[dict[str, object]] = []
    for term in terms:
        ids = term.get("source_category_ids")
        rows.append(
            {
                "sign": sign_glyph(term.get("sign") == "-"),
                "percent": term.get("coefficient_percent", ""),
                "category_ids": {int(str(i)) for i in ids}
                if isinstance(ids, tuple | list)
                else set(),
            }
        )
    return rows


def new_entry_context(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    tab: str,
    today: date,
    base_currency: str,
    posted: Mapping[str, str] | None = None,
    terms: Sequence[Mapping[str, object]] | None = None,
    errors: Mapping[str, str] | None = None,
    formula: tuple[str, str] | None = None,
) -> dict[str, object]:
    """Everything ``pages/entries/new-entry.html`` renders: defaults or the posted values.

    ``formula`` is the (figure, note) of the repeats hero in formula mode (``formula_hero``).
    """
    values = posted or {}
    cats = categories_service.list_all(conn, user_id)
    accounts = accounts_service.list_all(conn, user_id)
    picker = categories_service.picker_summary(conn, user_id, today=today)
    account = _picked(accounts, parse_int(values.get("account_id", "")), accounts[:1])
    category_view = _category_view(
        cats, picker, parse_int(values.get("category", values.get("category_id", "")))
    )
    currency = account.currency if account else base_currency
    hero = _hero(
        tab,
        values,
        currency=currency,
        sign=category_view["sign"],
        errors=errors or {},
        formula=formula,
    )
    return {
        "tab": tab,
        "action": TAB_ACTIONS[tab],
        **category_view,
        "hero": hero,
        "accounts": accounts,
        "selected_account_id": account.id if account else None,
        "currency": currency,
        "values": values,
        "today_iso": today.isoformat(),
        **_dependent_fields(
            conn, user_id, cats=cats, accounts=accounts, values=values, terms=terms
        ),
        "errors": {},
    }


def edit_context(
    conn: sqlite3.Connection,
    user_id: int,
    txn: Transaction,
    *,
    today: date,
    base_currency: str,
    posted: Mapping[str, str] | None = None,
    errors: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Everything ``fragments/dialogs/edit-transaction.html`` renders: stored or posted values.

    The amount is shown in the account's currency (``format_major``). A posted value (a 422, the
    hero refresh) wins over the stored one, field by field. The new-entry context supplies the
    picker, accounts and hero; this adds the edit action, the title, the transit destination and
    the credit line for the stored account.
    """
    values = {**_stored_values(conn, user_id, txn, base_currency), **(posted or {})}
    context = new_entry_context(
        conn,
        user_id,
        tab="happened",
        today=today,
        base_currency=base_currency,
        posted=values,
        errors=errors,
    )
    category = _picked(
        categories_service.list_all(conn, user_id, include_deleted=True),
        parse_int(values.get("category", "")),
    )
    transit = category is not None and category.direction == Direction.TRANSIT
    context["hero"] = _edit_hero(context, values["amount"], transit=transit)
    account_id = context["selected_account_id"]
    preview = _edit_preview(
        conn, user_id, txn, category=category, account_id=account_id, amount=values["amount"]
    )
    return {
        **context,
        "txn_id": txn.id,
        "action": f"{TAB_ACTIONS['happened']}/{txn.id}",
        "title": f"edit transaction \N{MIDDLE DOT} {category.name if category else ''}",
        "selected_dest_id": parse_int(values.get("dest_account_id", "")),
        "dest_visible": transit,
        "preview": preview,
    }


def _edit_hero(context: Mapping[str, object], amount: str, *, transit: bool) -> object:
    """The hero with the transit sign and a posted zero shown as ``0.00`` (the placeholder form)."""
    hero = context["hero"]
    currency = str(context["currency"])
    if not isinstance(hero, dict):
        return hero
    shown = dict(hero)
    if transit:
        shown["sign"] = _TRANSIT_GLYPH
    if parse_amount_minor(amount, currency) == 0:
        shown["amount_value"] = format_major(0, currency)
    return shown


def _stored_values(
    conn: sqlite3.Connection, user_id: int, txn: Transaction, base_currency: str
) -> dict[str, str]:
    """The stored transaction as form text (the amount in the account's currency)."""
    account = accounts_service.find_by_id(conn, user_id, txn.account_id, include_deleted=True)
    currency = account.currency if account else base_currency
    return {
        "category": str(txn.category_id),
        "account_id": str(txn.account_id),
        "amount": format_major(txn.amount, currency, grouped=True),
        "operation_date": txn.operation_date.isoformat(),
        "description": txn.description,
        "dest_account_id": str(txn.dest_account_id or ""),
    }


def _edit_preview(
    conn: sqlite3.Connection,
    user_id: int,
    txn: Transaction,
    *,
    category: Category | None,
    account_id: object,
    amount: str,
) -> limit_preview_service.LimitPreview | None:
    """The credit line of the edit dialog: the edited row is left out of the balance (ADR-0024)."""
    if category is None or not isinstance(account_id, int):
        return None
    return limit_preview_service.compute_limit_preview(
        conn,
        user_id,
        account_id=account_id,
        category_id=category.id,
        amount_raw=amount,
        exclude_txn_id=txn.id,
    )


def _dependent_fields(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    cats: Sequence[Category],
    accounts: Sequence[Account],
    values: Mapping[str, str],
    terms: Sequence[Mapping[str, object]] | None,
) -> dict[str, object]:
    """Conditions of the sections that show for a category or account, and the formula rows."""
    return {
        "transit_when": _when("category", [c.id for c in cats if c.direction == Direction.TRANSIT]),
        "credit_when": _when(
            "account_id", [a.id for a in accounts if a.is_liability and a.credit_limit_minor]
        ),
        "amount_source": values.get("amount_source", "fixed"),
        "components": _component_rows(terms or [dict(EMPTY_TERM_INPUT)]),
        "source_categories": formula_source_candidates(conn, user_id),
    }


def _hero(
    tab: str,
    values: Mapping[str, str],
    *,
    currency: str,
    sign: object,
    errors: Mapping[str, str],
    formula: tuple[str, str] | None,
) -> dict[str, object]:
    """The dialog hero: the amount input (account currency, category sign) or the formula result."""
    if tab == "repeats" and values.get("amount_source") == "formula":
        figure, note = formula or ("\N{EM DASH}", "")
        return {
            "currency": currency,
            "amount_id": "seg-amount-source",
            "output": True,
            "amount_value": figure,
            "note": note,
        }
    name = "default_amount" if tab == "repeats" else "amount"
    return {
        "currency": currency,
        "sign": sign,
        "amount_id": f"field-{name}",
        "amount_name": name,
        "amount_value": values.get(name, ""),
        "placeholder": format_major(0, currency),
        "error": errors.get(name),
    }


def formula_hero(
    conn: sqlite3.Connection,
    user_id: int,
    form: FormData | QueryParams,
    *,
    currency: str,
    today: date,
    fx: FormulaFx,
    rule_id: int | None = None,
) -> tuple[str, str]:
    """(figure, note) of the formula hero: the service's next amount, or why there is none.

    ``rule_id`` is the rule being edited, left out of its own sources (the edit dialog).
    """
    drafts = parse_draft_terms(form)
    if drafts is None:
        return "\N{EM DASH}", "invalid source category"
    return draft_hero(conn, user_id, drafts, currency=currency, today=today, fx=fx, rule_id=rule_id)


def draft_hero(
    conn: sqlite3.Connection,
    user_id: int,
    drafts: Sequence[formula_svc.DraftTerm],
    *,
    currency: str,
    today: date,
    fx: FormulaFx,
    rule_id: int | None = None,
) -> tuple[str, str]:
    """(figure, note) of the formula hero for already parsed terms."""
    result = formula_svc.preview(conn, user_id, today, rule_id, drafts, fx=fx, target_ccy=currency)
    if isinstance(result, formula_svc.PreviewOk):
        figure = format_figure(result.amount_minor, currency)
        return (
            figure,
            f"\N{RIGHTWARDS ARROW} next amount {format_money(result.amount_minor, currency)}",
        )
    return "\N{EM DASH}", result.message


def _category_view(
    cats: Sequence[Category], picker: categories_service.CategoryPicker, wanted: int | None
) -> dict[str, object]:
    """The chosen category: its id, the hero sign and the picker whose first chip it is.

    The handoff edit dialogs lead the recent chips with the selected category (checked), so
    the search button never carries a picked name on first render (``combobox.js`` sets it when
    the user picks from the list).
    """
    category = _picked(cats, wanted)
    if category is None:
        return {"selected_category_id": None, "picked_name": None, "sign": None, "picker": picker}
    return {
        "selected_category_id": category.id,
        "picked_name": None,
        "sign": _direction_sign(category.direction),
        "picker": categories_service.lead_with_selected(picker, category),
    }


def _picked[T: (Account, Category)](
    rows: Sequence[T], wanted: int | None, fallback: Sequence[T] = ()
) -> T | None:
    """The row with id ``wanted``, else the first of ``fallback``, else ``None``."""
    found = [r for r in rows if r.id == wanted] or list(fallback)
    return found[0] if found else None


def _when(name: str, ids: Sequence[int]) -> str:
    """A ``data-show-when`` condition on ``name`` holding for any of ``ids`` ('' when none)."""
    return f"{name}=" + "|".join(str(i) for i in ids) if ids else ""


def posted_entry(
    category: int,
    account_id: str,
    amount: str,
    *,
    operation_date: str,
    description: str,
    dest_account_id: str,
) -> dict[str, str]:
    """The posted create form as the dialog re-renders it."""
    return {
        "category": str(category or ""),
        "account_id": account_id,
        "amount": amount,
        "operation_date": operation_date,
        "description": description,
        "dest_account_id": dest_account_id,
    }


def check_promote_input(
    account: Account | None, operation_date: str, amount: str
) -> tuple[date | None, int | None, dict[str, str]]:
    """Date, amount (minor units) and field errors of a planned promote post."""
    op_date = parse_date(operation_date)
    errors: dict[str, str] = {} if op_date is not None else {"operation_date": "invalid date"}
    if account is None:
        return op_date, None, {**errors, "amount": "unknown account currency"}
    minor, err = positive_amount(amount, account.currency)
    return op_date, minor, ({**errors, "amount": err} if err else errors)


def promote_context(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    action: str,
    category_id: int,
    account: Account | None,
    amount_minor: int,
    date_value: date,
    note_value: str,
    base_currency: str,
    recurring: bool = False,
    notes: Sequence[str] = (),
    posted: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Everything ``pages/entries/promote.html`` renders: stored prefill or posted values."""
    values = posted or {}
    cat = categories_service.find_by_id(conn, user_id, category_id, include_deleted=True)
    currency = account.currency if account else base_currency
    name = cat.name if cat else ""
    return {
        "dialog_id": "promote-dialog",
        "title": f"promote · {name}" if recurring else f"promote to actual · {name}",
        "action": action,
        "currency": currency,
        "sign": _direction_sign(cat.direction) if cat else None,
        "amount_value": values.get("amount", format_major(amount_minor, currency, grouped=True)),
        "date_value": values.get("operation_date", date_value.isoformat()),
        "note_value": values.get("description", note_value),
        "notes": list(notes),
        "errors": {},
    }


def account_choice(account_id: str) -> int:
    """The posted account id; ``0`` (no such account) when blank or not a number."""
    return parse_int(account_id) or 0


def category_choice(category_id: str, category: str) -> int:
    """The posted category id: ``category_id`` or the picker's ``category``; ``0`` when blank."""
    return parse_int(category_alias(category_id, category)) or 0


def pick_category_error(errors: dict[str, str], category: int) -> dict[str, str]:
    """A blank pick reads "Pick a category" instead of "unknown category" (handoff error state)."""
    if category == 0 and "category_id" in errors:
        return {**errors, "category_id": "Pick a category"}
    return errors


def save_txn(
    conn: sqlite3.Connection, user_id: int, check: EntryCheck, description: str
) -> Transaction:
    """Create the transaction a valid create check describes."""
    op_date, minor = check.valid_values()
    return transactions_service.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=op_date,
            category_id=require_present(check.category, "validated category").id,
            account_id=require_present(check.account, "validated account").id,
            amount=minor,
            description=description,
            dest_account_id=check.dest_id,
        ),
    )


def save_txn_update(
    conn: sqlite3.Connection, user_id: int, txn_id: int, check: EntryCheck, description: str
) -> Transaction:
    """Apply the edit a valid update check describes."""
    op_date, minor = check.valid_values()
    return transactions_service.update(
        conn,
        user_id,
        txn_id,
        PatchTransaction(
            operation_date=op_date,
            category_id=require_present(check.category, "validated category").id,
            account_id=require_present(check.account, "validated account").id,
            amount=minor,
            description=description,
            dest_account_id=check.dest_id,
        ),
    )


def save_planned_update(
    conn: sqlite3.Connection,
    user_id: int,
    planned_id: int,
    check: EntryCheck,
    description: str,
) -> None:
    """Store the edit a valid update check describes."""
    op_date, minor = check.valid_values()
    planned_service.update(
        conn,
        user_id,
        planned_id,
        PatchPlannedTransaction(
            operation_date=op_date,
            category_id=require_present(check.category, "validated category").id,
            account_id=require_present(check.account, "validated account").id,
            amount=minor,
            description=description,
        ),
    )


def save_planned(
    conn: sqlite3.Connection, user_id: int, check: EntryCheck, description: str
) -> PlannedTransaction:
    """Create the planned transaction a valid create check describes."""
    op_date, minor = check.valid_values()
    return planned_service.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=op_date,
            category_id=require_present(check.category, "validated category").id,
            account_id=require_present(check.account, "validated account").id,
            amount=minor,
            description=description,
            dest_account_id=check.dest_id,
        ),
    )
