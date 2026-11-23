"""Per-tab export links for the Ledger page (T-UR34b, ADR-0134 section 6).

A pure view-model helper: the live filter state in, the csv and parquet hrefs
out, so templates render a link without building query strings themselves.
Recurring has no export (ADR-0134 section 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final
from urllib.parse import urlencode

from budget_planner.web.ledger_types import LedgerFilters, ViewKind

_EXPORT_PATHS: Final[Mapping[ViewKind, str]] = MappingProxyType(
    {
        "actual": "/transactions/export",
        "planned": "/planned/export",
    }
)


@dataclass(frozen=True, slots=True)
class ExportLinks:
    """The csv and parquet hrefs of one tab, both carrying the live filters."""

    csv: str
    parquet: str


def filter_query(filters: LedgerFilters) -> list[tuple[str, str]]:
    """The non-empty filter params, in a stable order, as the export routes read them."""
    pairs: list[tuple[str, str]] = []
    if filters.date_from is not None:
        pairs.append(("date_from", filters.date_from.isoformat()))
    if filters.date_to is not None:
        pairs.append(("date_to", filters.date_to.isoformat()))
    pairs.extend(("account_id", str(i)) for i in filters.account_ids)
    pairs.extend(("category_id", str(i)) for i in filters.category_ids)
    if filters.direction:
        pairs.append(("direction", filters.direction))
    if filters.search:
        pairs.append(("q", filters.search))
    return pairs


def export_links(view: ViewKind, filters: LedgerFilters) -> ExportLinks | None:
    """Export hrefs for ``view`` under ``filters``; ``None`` for a tab without export."""
    path = _EXPORT_PATHS.get(view)
    if path is None:
        return None
    base = filter_query(filters)
    return ExportLinks(
        csv=f"{path}?{urlencode([*base, ('format', 'csv')])}",
        parquet=f"{path}?{urlencode([*base, ('format', 'parquet')])}",
    )
