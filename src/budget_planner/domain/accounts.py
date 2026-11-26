"""Account entity + DTOs + stats."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime

from budget_planner.domain.limits import name_error
from budget_planner.domain.money import ISO_4217_CURRENCIES

ISO_CURRENCY_LENGTH = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class Account:
    """Persisted account row."""

    id: int
    user_id: int
    name: str
    type: str | None
    currency: str
    opening_balance: int
    is_liability: bool
    credit_limit_minor: int | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewAccount:
    """Insertable fields for a new account.

    `currency` is immutable per ADR-0006; omitted from `PatchAccount`.
    """

    name: str
    currency: str
    opening_balance: int = 0
    type: str | None = None
    is_liability: bool = False
    credit_limit_minor: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PatchAccount:
    """Partial update DTO. `None` values mean "do not change".

    ``credit_limit_minor`` + ``clear_credit_limit`` carry a sentinel pair:
    ``None`` with ``clear_credit_limit=False`` means "no change"; any truthy
    ``clear_credit_limit`` writes ``NULL`` regardless of the limit value.
    """

    name: str | None = None
    type: str | None = None
    opening_balance: int | None = None
    is_liability: bool | None = None
    credit_limit_minor: int | None = None
    clear_credit_limit: bool = False

    def as_dict(self) -> dict[str, object]:
        """Return only the fields set to a non-None value.

        ``clear_credit_limit`` is a control flag, not a persisted field, so
        it is always excluded from the dict and interpreted by the repository.
        """
        out: dict[str, object] = {}
        for f in fields(self):
            if f.name == "clear_credit_limit":
                continue
            value = getattr(self, f.name)
            if value is not None:
                out[f.name] = value
        if self.clear_credit_limit:
            out["credit_limit_minor"] = None
        return out


@dataclass(frozen=True, slots=True, kw_only=True)
class AccountStats:
    """Derived stats returned by the Phase 2 balance service.

    - ``balance`` / ``base_balance`` are minor units; ``base_balance`` is set
      by callers that convert through FX (service returns ``balance`` in it
      until that conversion happens, so unit tests do not depend on FX).
    - ``avg_inflow_minor`` / ``avg_outflow_minor`` cover only
      ``income`` / ``expense`` legs (transit + adjustment skipped — see
      T-021 plan).
    - ``last_txn_date`` is ISO ``YYYY-MM-DD`` for easy template rendering.
    """

    account_id: int
    balance: int
    base_balance: int
    txn_count: int
    last_txn_date: str | None
    avg_inflow_minor: int = 0
    avg_outflow_minor: int = 0


def currency_error(currency: str) -> str | None:
    """Form error for a currency that is not a known ISO 4217 code (or None).

    A malformed code keeps "ISO 4217 code required"; a well-formed one the app does not know
    (``XYZ``) is "Unknown currency code" (handoff overlays new-account--error).
    """
    if not (len(currency) == ISO_CURRENCY_LENGTH and currency.isalpha()):
        return "ISO 4217 code required"
    return None if currency in ISO_4217_CURRENCIES else "Unknown currency code"


def credit_limit_error(limit_minor: int | None) -> str | None:
    """A stored credit limit is positive; ``None`` (no limit) is valid."""
    if limit_minor is not None and limit_minor <= 0:
        return "positive credit limit required"
    return None


def _non_empty(errors: dict[str, str | None]) -> dict[str, str]:
    return {k: v for k, v in errors.items() if v is not None}


def new_account_errors(data: NewAccount) -> dict[str, str]:
    """Field errors for a new account command (empty when valid)."""
    return _non_empty(
        {
            "name": name_error(data.name),
            "currency": currency_error(data.currency),
            "credit_limit": credit_limit_error(data.credit_limit_minor),
        }
    )


KIND_FIXED_MESSAGE = "can't be changed after the account is created"


def patch_account_errors(patch: PatchAccount) -> dict[str, str]:
    """Field errors for an account patch (empty when valid)."""
    return _non_empty(
        {
            "name": None if patch.name is None else name_error(patch.name),
            "credit_limit": credit_limit_error(patch.credit_limit_minor),
        }
    )


@dataclass(frozen=True, slots=True)
class AccountReferences:
    """Live rows that reference an account (T-UR33, ADR-0134 §3).

    "Blocked by recurring only" is ``recurring > 0`` with the other two at 0.
    """

    transactions: int
    planned: int
    recurring: int

    @property
    def total(self) -> int:
        return self.transactions + self.planned + self.recurring
