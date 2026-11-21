"""Shared enums used across repositories, services, and the web layer.

StrEnum values intentionally match the SQL CHECK constraint literals in
`migrations/0002_core_schema.sql`.
"""

from __future__ import annotations

from enum import StrEnum


class Direction(StrEnum):
    """Transaction / category direction. See ADR-0008."""

    INCOME = "income"
    EXPENSE = "expense"
    TRANSIT = "transit"
    ADJUSTMENT = "adjustment"


class Cadence(StrEnum):
    """Recurring-rule cadence. See ADR-0013."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


def months_per_cadence(cadence: Cadence) -> int:
    """Calendar months between two occurrences of ``cadence`` (the one mapping, ADR-0013)."""
    if cadence is Cadence.QUARTERLY:
        return 3
    if cadence is Cadence.YEARLY:
        return 12
    return 1


class OverrideState(StrEnum):
    """State of a sparse recurring-rule override. See ADR-0013."""

    SKIPPED = "skipped"
    OVERRIDDEN = "overridden"


class AuditOperation(StrEnum):
    """Audit log operation. See ADR-0019."""

    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    UNDELETE = "undelete"
