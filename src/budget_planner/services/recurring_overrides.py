"""Apply the recurring-override state machine to canonical occurrences (T-Q243, ADR-0038).

Split out of ``services.recurring`` so ``services.recurring_formula`` and
``services.recurring`` share it without importing each other.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Iterable, Sequence

from budget_planner.domain.enums import OverrideState
from budget_planner.domain.recurring import Occurrence, RecurringOverride

logger = logging.getLogger(__name__)


def _apply_single_override(occ: Occurrence, override: RecurringOverride) -> Occurrence | None:
    """Return the overridden occurrence, or ``None`` if ``state=skipped``."""
    if override.state is OverrideState.SKIPPED:
        return None
    new_amount = override.amount_override if override.amount_override is not None else occ.amount
    new_description = (
        override.description_override
        if override.description_override is not None
        else occ.description
    )
    new_effective = (
        override.date_override if override.date_override is not None else occ.occurrence_date
    )
    return Occurrence(
        rule_id=occ.rule_id,
        occurrence_date=occ.occurrence_date,  # canonical key preserved
        effective_date=new_effective,
        category_id=occ.category_id,
        account_id=occ.account_id,
        dest_account_id=occ.dest_account_id,
        amount=new_amount,
        description=new_description,
        is_overridden=True,
        is_skipped=False,
    )


def apply_overrides(
    occurrences: Sequence[Occurrence],
    overrides: Iterable[RecurringOverride],
) -> tuple[Occurrence, ...]:
    """Apply the ``(skipped | overridden)`` state machine.

    Keyed by the ORIGINAL ``occurrence_date``, not the overridden one. Orphan
    overrides (no matching canonical occurrence) are dropped with a DEBUG log.
    Duplicates on the same key log a WARNING; last-wins by sort order on ``id``.
    """
    # Group overrides by occurrence_date, warn on duplicates.
    by_date: dict[dt.date, RecurringOverride] = {}
    seen: set[dt.date] = set()
    canonical_dates = {o.occurrence_date for o in occurrences}
    for override in sorted(overrides, key=lambda o: o.id):
        if override.occurrence_date in seen:
            logger.warning(
                "overrides collide on (rule_id=%s, occurrence_date=%s); last-wins",
                override.rule_id,
                override.occurrence_date,
            )
        seen.add(override.occurrence_date)
        if override.occurrence_date not in canonical_dates:
            logger.debug(
                "orphan override dropped: rule_id=%s date=%s",
                override.rule_id,
                override.occurrence_date,
            )
            continue
        by_date[override.occurrence_date] = override

    out: list[Occurrence] = []
    for occ in occurrences:
        match = by_date.get(occ.occurrence_date)
        if match is None:
            out.append(occ)
            continue
        updated = _apply_single_override(occ, match)
        if updated is not None:
            out.append(updated)
    # Sort by effective_date (overrides may shift dates), stable on occurrence_date.
    out.sort(key=lambda o: (o.effective_date, o.occurrence_date))
    return tuple(out)
