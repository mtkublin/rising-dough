"""T-Q06 repro: silent FX fallback to rate 1 (and currency-blind Ledger strips).

Builds /tmp/audit-C-fx.sqlite from /tmp/audit-C.sqlite: account 2 becomes a 1000.00 EUR
account, no FX rate is cached and the FX API is made unreachable (httpx ConnectError),
which is the exact failure condition ADR-0006 describes.

Run:
    cp /tmp/audit-C.sqlite /tmp/audit-C-fx.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C-fx.sqlite PYTHONPATH=. \
      uv run python docs/plans/quality-audit/repro/C/repro_fx_fallback.py
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import sys

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")
PATH = URL.removeprefix("sqlite:///")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TODAY = dt.date.today()  # noqa: DTZ011
db = sqlite3.connect(PATH)
db.execute("UPDATE accounts SET currency='EUR', opening_balance=100000 WHERE id=2")
db.execute("DELETE FROM fx_rates")
db.execute("DELETE FROM planned_transactions")
for cat, acc, amt in ((7, 2, 50000), (7, 1, 30000), (3, 1, 100000)):
    db.execute(
        "INSERT INTO planned_transactions(user_id, operation_date, category_id, account_id, amount)"
        " VALUES (1, ?, ?, ?, ?)",
        ((TODAY + dt.timedelta(days=3)).isoformat(), cat, acc, amt),
    )
db.commit()
db.close()


def _unreachable(self, *a, **k):  # type: ignore[no-untyped-def]  # noqa: ANN001, ARG001
    raise httpx.ConnectError("simulated: frankfurter unreachable")


httpx.Client.get = _unreachable  # type: ignore[method-assign,assignment]

from budget_planner.config import Settings  # noqa: E402
from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.services import budget as budget_svc  # noqa: E402
from budget_planner.web import today_data  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from tests.auth_support import login_cookie  # noqa: E402

settings = Settings()
conn = get_connection(settings)

print("== F1: Today fortune (web/today_data.py:129) ==")
rows, totals, fortune = today_data.collect_account_rows(conn, 1, "PLN")
eur = next(r for r in rows if r.currency == "EUR")
print(f"EUR account native={eur.balance_minor} base={eur.balance_base_minor} (rate used = 1)")
print(f"fortune_base={fortune}; same fortune if EUR were excluded = {fortune - eur.balance_base_minor}")

print("\n== F2: budget converters (services/budget.py:81,112) ==")
conv = budget_svc.base_amount_converter(conn, 1, today=TODAY, base_currency="PLN")
print("1000.00 EUR planned item -> base minor:", conv(2, 100000), "(native 100000 passes through)")

print("\n== F3: Ledger planned strip is direction- and currency-blind, label hard-coded PLN ==")
app = create_app(settings)
name, value = login_cookie(settings)
with TestClient(app, base_url="https://testserver") as c:
    c.cookies.set(name, value)
    html = c.get("/ledger?view=planned").text
m = re.search(r"<strong>(\d+)</strong> items.*?<strong class=\"numeric\">([^<]+)</strong>", html, re.S)
print("strip:", m.groups() if m else "NOT FOUND")
print(
    "planned rows: expense 500.00 EUR + expense 300.00 PLN + income 1000.00 PLN"
    " -> expected net (PLN-only, EUR unconverted) is not 1,800.00"
)

print("\n== F4: pages with an EUR account, no cached rate, API unreachable ==")
with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
    c.cookies.set(name, value)
    for route in ("/today", "/forecast", "/budget", "/plan", "/accounts"):
        resp = c.get(route)
        print(f"{route:10} -> HTTP {resp.status_code}")
