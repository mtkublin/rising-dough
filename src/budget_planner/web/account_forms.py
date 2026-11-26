"""Account form parsing (T-Q266): submitted strings to a domain command or per-field errors.

Pure request parsing for the accounts router; amounts via ``domain.money``/``web.params``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.accounts import (
    KIND_FIXED_MESSAGE,
    Account,
    NewAccount,
    PatchAccount,
    currency_error,
)
from budget_planner.domain.limits import name_error
from budget_planner.domain.money import parse_amount_minor
from budget_planner.web.accounts_view import account_dialog
from budget_planner.web.dialogs import invalid_dialog_response
from budget_planner.web.params import credit_limit_amount

ACCOUNT_DIALOG = "pages/accounts/dialog-account.html"
_TRUE_FLAGS = frozenset({"on", "true", "1"})


@dataclass(frozen=True)
class ParsedNewAccount:
    """Result of parsing the create form: a command, or per-field errors."""

    command: NewAccount | None
    errors: dict[str, str] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)  # the submitted strings, to re-render


@dataclass(frozen=True)
class ParsedAccountPatch:
    """Result of parsing the edit form: a patch, or per-field errors."""

    patch: PatchAccount | None
    errors: dict[str, str] = field(default_factory=dict)
    values: dict[str, str] = field(default_factory=dict)  # the submitted strings, to re-render


def parse_liability(raw: str) -> bool:
    """Checkbox text to a bool."""
    return raw.strip().lower() in _TRUE_FLAGS


def _currency_error(cur: str) -> dict[str, str]:
    bad = currency_error(cur)
    return {} if bad is None else {"currency": bad}


def _limit_for(
    *, liability: bool, currency: str, raw: str, errors: dict[str, str]
) -> tuple[int | None, dict[str, str]]:
    """Credit limit for a liability (needs a valid currency); errors are returned, not mutated."""
    if not liability or "currency" in errors:
        return None, {}
    minor, limit_err = credit_limit_amount(raw, currency)
    return minor, ({} if limit_err is None else {"credit_limit": limit_err})


def parse_new_account(
    *,
    name: str,
    currency: str,
    opening_balance: str,
    account_type: str,
    is_liability: str,
    credit_limit: str,
) -> ParsedNewAccount:
    """Validate the create form; the result keeps the submitted strings."""
    parsed = _parse_new_account(
        name=name,
        currency=currency,
        opening_balance=opening_balance,
        account_type=account_type,
        is_liability=is_liability,
        credit_limit=credit_limit,
    )
    values = {
        "name": name,
        "currency": currency,
        "opening_balance": opening_balance,
        "type": account_type,
        "is_liability": is_liability,
        "credit_limit": credit_limit,
    }
    return replace(parsed, values=values)


def _parse_new_account(
    *,
    name: str,
    currency: str,
    opening_balance: str,
    account_type: str,
    is_liability: str,
    credit_limit: str,
) -> ParsedNewAccount:
    """Validate the create form."""
    cur = currency.upper().strip()
    opening = parse_amount_minor(opening_balance or "0", cur)
    liability = parse_liability(is_liability)
    errors = {
        **_currency_error(cur),
        **({} if opening is not None else {"opening_balance": "invalid number"}),
        **({} if (bad := name_error(name)) is None else {"name": bad}),
    }
    limit_minor, limit_errors = _limit_for(
        liability=liability, currency=cur, raw=credit_limit, errors=errors
    )
    errors = {**errors, **limit_errors}
    if errors:
        return ParsedNewAccount(command=None, errors=errors)
    return ParsedNewAccount(
        command=NewAccount(
            name=name.strip(),
            currency=cur,
            opening_balance=opening or 0,
            type=account_type or None,
            is_liability=liability,
            credit_limit_minor=limit_minor,
        )
    )


def parse_account_patch(
    account: Account, *, name: str, account_type: str, is_liability: str, credit_limit: str
) -> ParsedAccountPatch:
    """Validate the edit form against the stored account; the result keeps the submitted strings."""
    parsed = _parse_account_patch(
        account,
        name=name,
        account_type=account_type,
        is_liability=is_liability,
        credit_limit=credit_limit,
    )
    values = {
        "name": name,
        "type": account_type,
        "is_liability": is_liability,
        "credit_limit": credit_limit,
    }
    return replace(parsed, values=values)


def _parse_account_patch(
    account: Account, *, name: str, account_type: str, is_liability: str, credit_limit: str
) -> ParsedAccountPatch:
    """Validate the edit form against the stored account (its currency fixes the limit unit)."""
    errors = {
        **({} if (bad_name := name_error(name)) is None else {"name": bad_name}),
        **(
            {}
            if parse_liability(is_liability) == account.is_liability
            else {"is_liability": KIND_FIXED_MESSAGE}
        ),
    }
    if errors:
        return ParsedAccountPatch(patch=None, errors=errors)
    liability = account.is_liability
    limit_minor: int | None = None
    if liability:
        limit_minor, limit_err = credit_limit_amount(credit_limit, account.currency)
        if limit_err is not None:
            return ParsedAccountPatch(patch=None, errors={"credit_limit": limit_err})
    return ParsedAccountPatch(
        patch=PatchAccount(
            name=name.strip(),
            type=account_type or None,
            is_liability=liability,
            credit_limit_minor=limit_minor,
            clear_credit_limit=not liability,
        )
    )


def invalid_account_response(
    request: Request,
    acc: Account | None,
    *,
    values: dict[str, str],
    errors: dict[str, str],
    base_currency: str,
    today: date,
) -> Response:
    """The account dialog again with the typed values and its field errors (422)."""
    dlg = account_dialog(
        acc, values=values, base_currency=base_currency, today=today, errors=errors
    )
    return invalid_dialog_response(request, ACCOUNT_DIALOG, {"dlg": dlg}, errors)
