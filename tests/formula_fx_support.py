"""Test helper: the cache-only :class:`FormulaFx` a request would build (T-Q286)."""

from __future__ import annotations

import datetime as dt
import sqlite3

from budget_planner.services.fx import BaseCurrency
from budget_planner.services.recurring_formula import FormulaFx, formula_fx_for

TARGET_CCY = "PLN"
_TODAY = dt.date(2026, 11, 22)


def formula_fx_of(conn: sqlite3.Connection, user_id: int, *, today: dt.date = _TODAY) -> FormulaFx:
    """FormulaFx over the cached ``fx_rates`` with PLN base and the user's account currencies."""
    return formula_fx_for(conn, user_id, BaseCurrency("PLN"), today)
