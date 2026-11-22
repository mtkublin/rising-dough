"""Account form parsing (T-Q266): submitted strings to a domain command or per-field errors.

Pure request parsing for the accounts router; amounts via ``domain.money``/``web.params``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from budget_planner.domain.accounts import Account, NewAccount, PatchAccount, currency_error
from budget_planner.domain.limits import name_error
from budget_planner.domain.money import parse_amount_minor
from budget_planner.web.params import credit_limit_amount

_TRUE_FLAGS = frozenset({"on", "true", "1"})
_SNAPSHOT_FLAGS = frozenset({"1", "on", "true", "yes"})


@dataclass(frozen=True)
class ParsedNewAccount:
    """Result of parsing the create form: a command, or per-field errors."""

    command: NewAccount | None
    errors: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedAccountPatch:
    """Result of parsing the edit form: a patch, or per-field errors."""

    patch: PatchAccount | None
    errors: dict[str, str] = field(default_factory=dict)


def parse_liability(raw: str) -> bool:
    """Checkbox text to a bool."""
    return raw.strip().lower() in _TRUE_FLAGS


def parse_save_snapshot(raw: str) -> bool:
    """Reconcile-modal "also save a snapshot" checkbox text to a bool."""
    return raw.strip().lower() in _SNAPSHOT_FLAGS


def parse_category_id(raw: str) -> int | None:
    """Optional category select value to an id (blank or non-numeric is ``None``)."""
    text = raw.strip()
    return int(text) if text.isdigit() else None


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
    """Validate the edit form against the stored account (its currency fixes the limit unit)."""
    if (bad_name := name_error(name)) is not None:
        return ParsedAccountPatch(patch=None, errors={"name": bad_name})
    liability = parse_liability(is_liability)
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
