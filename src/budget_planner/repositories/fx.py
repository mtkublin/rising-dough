"""FX rate repository — append-only; unique on (date, from_ccy, to_ccy)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget_planner.domain.fx import FxRate, NewFxRate
from budget_planner.repositories._shared import mutate, parse_dt_required

_COLUMNS = "id, date, from_ccy, to_ccy, rate, fetched_at"


def _row_to_rate(row: sqlite3.Row) -> FxRate:
    return FxRate(
        id=row["id"],
        date=date.fromisoformat(row["date"]),
        from_ccy=row["from_ccy"],
        to_ccy=row["to_ccy"],
        rate=Decimal(row["rate"]),
        fetched_at=parse_dt_required(row["fetched_at"]),
    )


def find_rate(
    conn: sqlite3.Connection,
    rate_date: date,
    from_ccy: str,
    to_ccy: str,
) -> FxRate | None:
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM fx_rates WHERE date = ? AND from_ccy = ? AND to_ccy = ?",
        (rate_date.isoformat(), from_ccy, to_ccy),
    ).fetchone()
    return _row_to_rate(row) if row is not None else None


def latest_rate(
    conn: sqlite3.Connection,
    from_ccy: str,
    to_ccy: str,
    *,
    on_or_before: date | None = None,
) -> FxRate | None:
    sql = f"SELECT {_COLUMNS} FROM fx_rates WHERE from_ccy = ? AND to_ccy = ?"
    params: list[object] = [from_ccy, to_ccy]
    if on_or_before is not None:
        sql += " AND date <= ?"
        params.append(on_or_before.isoformat())
    sql += " ORDER BY date DESC, id DESC LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    return _row_to_rate(row) if row is not None else None


def list_rates_to(conn: sqlite3.Connection, to_ccy: str) -> list[FxRate]:
    """Every cached rate into ``to_ccy``, oldest first per source currency."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM fx_rates WHERE to_ccy = ? ORDER BY from_ccy, date, id",
        (to_ccy,),
    ).fetchall()
    return [_row_to_rate(row) for row in rows]


def list_recent(conn: sqlite3.Connection, *, limit: int = 50) -> list[FxRate]:
    """Return the most-recently fetched FX rates, newest first.

    Read-only; used by the Settings drawer FX tab (T-067). Ordering by
    `fetched_at DESC` surfaces freshly refreshed rates first, with a stable
    secondary sort on `date` for determinism when fetches batch together.
    """
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM fx_rates ORDER BY fetched_at DESC, date DESC, id DESC LIMIT ?",
        (int(limit),),
    ).fetchall()
    return [_row_to_rate(row) for row in rows]


def upsert_rate(conn: sqlite3.Connection, data: NewFxRate) -> FxRate:
    existing = find_rate(conn, data.date, data.from_ccy, data.to_ccy)
    prev = existing

    def _upsert_rate_action(c: sqlite3.Connection) -> tuple[int, FxRate]:
        if existing is None:
            cursor = c.execute(
                "INSERT INTO fx_rates(date, from_ccy, to_ccy, rate) VALUES (?, ?, ?, ?)",
                (
                    data.date.isoformat(),
                    data.from_ccy,
                    data.to_ccy,
                    str(data.rate),
                ),
            )
            new_id = int(cursor.lastrowid or 0)
        else:
            c.execute(
                "UPDATE fx_rates SET rate = ?, "
                "fetched_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
                "WHERE id = ?",
                (str(data.rate), existing.id),
            )
            new_id = existing.id
        row = c.execute(f"SELECT {_COLUMNS} FROM fx_rates WHERE id = ?", (new_id,)).fetchone()
        return new_id, _row_to_rate(row)

    return mutate(
        conn,
        entity_type="fx_rate",
        operation="update" if prev is not None else "create",
        prev=prev,
        action=_upsert_rate_action,
        user_id=None,
    )


__all__ = ["find_rate", "latest_rate", "list_rates_to", "list_recent", "upsert_rate"]
