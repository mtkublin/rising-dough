"""Forecast cash events (T-Q242, split from ``forecast.py``): signed events from recurring items."""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from dataclasses import dataclass

from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import signed_legs
from budget_planner.services import recurring as recurring_svc

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class CashEvent:
    """Signed per-account cash movement scheduled on a particular date."""

    on_date: dt.date
    account_id: int
    amount_minor: int


# ---------------------------------------------------------------------------
# event emission
# ---------------------------------------------------------------------------
def signed_events_for_direction(
    direction: Direction,
    operation_date: dt.date,
    account_id: int,
    dest_account_id: int | None,
    amount_minor: int,
) -> tuple[CashEvent, ...]:
    """Return the per-account cash events for one planned/virtual leg.

    Adapter over ``domain.transactions.signed_legs`` but for forward-looking events
    (operates on dates + raw ints rather than ``Transaction`` rows). Returns
    ``()`` for adjustments — planned adjustments are unsupported (ADR-0011
    + T-023 guard); surviving rows are skipped defensively with a DEBUG log.
    """
    if direction is Direction.ADJUSTMENT:
        logger.debug(
            "forecast skipping adjustment-direction planned leg on %s acct=%s",
            operation_date,
            account_id,
        )
        return ()
    if direction is Direction.TRANSIT:
        if dest_account_id is None:
            raise ValueError("transit event missing dest_account_id")
        if dest_account_id == account_id:
            raise ValueError("transit source and dest must differ")
    return tuple(
        CashEvent(on_date=operation_date, account_id=leg.account_id, amount_minor=leg.amount_minor)
        for leg in signed_legs(direction, amount_minor, account_id, dest_account_id)
    )


def events_for_item(item: recurring_svc.PendingItem) -> tuple[CashEvent, ...]:
    return signed_events_for_direction(
        direction=item.direction,
        operation_date=item.on_date,
        account_id=item.account_id,
        dest_account_id=item.dest_account_id,
        amount_minor=item.amount,
    )


# ---------------------------------------------------------------------------
# event collection
# ---------------------------------------------------------------------------
def collect_events(
    conn: sqlite3.Connection,
    user_id: int,
    today: dt.date,
    end_date: dt.date,
) -> dict[dt.date, list[CashEvent]]:
    """Return per-date cash events sourced from planned rows + virtual occurrences.

    Overdue unpromoted items are counted and placed on ``today + 1`` (ADR-0105
    amendment 2026-11-21, OQ-6 default).
    """
    event_start = today + dt.timedelta(days=1)
    if event_start > end_date:
        return {}

    events: dict[dt.date, list[CashEvent]] = {}
    for item in recurring_svc.pending_occurrences(
        conn,
        user_id,
        start=event_start,
        end=end_date + dt.timedelta(days=1),
        today=today,
        include_overdue=True,
        overdue_on=event_start,
    ):
        for ev in events_for_item(item):
            events.setdefault(ev.on_date, []).append(ev)
    return events
