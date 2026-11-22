"""Shared types for the ledger router (T-064).

Keeps the ``ViewKind`` literal + a frozen filter DTO out of the router module
so templates and tests can import them without creating circular deps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, get_args

from budget_planner.web.params import query_choice

ViewKind = Literal["actual", "planned", "recurring"]

_DEFAULT_VIEW: ViewKind = "actual"


def view_kinds() -> tuple[ViewKind, ...]:
    """Return the ordered tuple of valid ledger view kinds."""
    return tuple(get_args(ViewKind))


def query_view(value: str | None) -> ViewKind:
    """Return ``value`` if it is a valid :data:`ViewKind`; absent or empty is the default.

    An unknown value raises ``ParamError`` (a 422 naming ``view``).
    """
    return query_choice("view", value, view_kinds()) or _DEFAULT_VIEW


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerFilters:
    """Shared filter DTO used across all three ledger views.

    Only the fields consumed by every underlying repository live here. Per-view
    nuances (e.g. ``promoted`` for planned) are mapped at dispatch time.
    """

    date_from: date | None = None
    date_to: date | None = None
    account_ids: tuple[int, ...] = ()
    category_ids: tuple[int, ...] = ()
    direction: str | None = None
    search: str | None = None
    page: int = 1
    page_size: int = 50


__all__ = ["LedgerFilters", "ViewKind", "query_view", "view_kinds"]
