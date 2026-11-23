"""Human labels for form field names in the 422 summary (ADR-0147 §3, gap G11).

Pure data and two lookups: the label of a field key, never the raw key, and
the per-field summary entries the 422 page renders.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

FIELD_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "account_id": "Account",
        "actual_balance": "Actual balance",
        "amount": "Amount",
        "cadence": "Repeats",
        "category_id": "Category",
        "color": "Colour",
        "dest_account_id": "Destination account",
        "email": "Email",
        "month": "Month",
        "name": "Name",
        "operation_date": "Date",
        "start_date": "Start date",
        "year": "Year",
    }
)


def field_label(name: str) -> str:
    """Human label for a field key; unknown keys become title-cased words."""
    known = FIELD_LABELS.get(name)
    if known is not None:
        return known
    return name.replace("_", " ").strip().title()


def field_summary(fields: Mapping[str, str]) -> tuple[tuple[str, str, str], ...]:
    """(field name, human label, message) per invalid field, in input order."""
    return tuple((name, field_label(name), message) for name, message in fields.items())
