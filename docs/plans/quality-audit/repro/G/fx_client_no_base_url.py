"""G-03 repro: FX remote fetch is built with a relative URL but no client has a base_url.

Run: uv run python docs/plans/quality-audit/repro/G/fx_client_no_base_url.py
No network needed: httpx rejects the relative URL before any I/O.
"""
import datetime as dt
import sqlite3

import httpx

from budget_planner.services import fx

with httpx.Client(timeout=5.0) as http:  # exactly how web/today_data.py:124, routers/forecast.py:49, services/forecast.py:950 build it
    try:
        fx._fetch_remote(http, dt.date(2026, 11, 19), "EUR", "PLN")
    except Exception as exc:  # noqa: BLE001
        print(type(exc).__mro__[:4])
        print("caught by get_rate's `except httpx.HTTPError`:", isinstance(exc, httpx.HTTPError))
        print(exc)
