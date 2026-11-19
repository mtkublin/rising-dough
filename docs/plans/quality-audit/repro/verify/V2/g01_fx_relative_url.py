"""V2 repro for G-01: services.fx.get_rate with a base_url-less httpx.Client, as built at
web/today_data.py:124 and web/routers/forecast.py:49. In-memory DB; a MockTransport guarantees
nothing touches the network (a relative URL is rejected by httpx before any I/O anyway).

Run: uv run python docs/plans/quality-audit/repro/verify/V2/g01_fx_relative_url.py
"""

import datetime as dt
import sqlite3

import httpx

from budget_planner.db.migrate import apply_migrations
from budget_planner.services import fx

conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
apply_migrations(conn)

sent: list[str] = []


def handler(request: httpx.Request) -> httpx.Response:
    sent.append(str(request.url))
    return httpx.Response(200, json={"rates": {"PLN": 4.0}})


# Prod construction is httpx.Client(timeout=5.0) with no base_url.
client = httpx.Client(timeout=5.0)  # real transport: relative URL fails before any I/O
day = dt.date(2026, 11, 19)
try:
    fx._fetch_remote(client, day, "USD", "PLN")
except Exception as e:  # noqa: BLE001
    print("fetch_remote raises:", type(e).__name__, "|", e, "| is httpx.HTTPError:", isinstance(e, httpx.HTTPError))
print("requests that left the client:", sent)
try:
    print("get_rate returned", fx.get_rate(conn, client, day, "USD", "PLN"))
except fx.FxUnavailableError as e:
    print("get_rate -> FxUnavailableError (today_data.py then sets rate=Decimal('1')):", e)

client2 = httpx.Client(base_url="https://api.frankfurter.app", transport=httpx.MockTransport(handler))
print("with base_url get_rate ->", fx.get_rate(conn, client2, day, "USD", "PLN"), "| requests:", sent)
