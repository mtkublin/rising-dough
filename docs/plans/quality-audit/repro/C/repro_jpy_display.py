"""T-Q06 repro: zero-decimal currency (JPY) shown 100x too small on /today (hard-coded / 100.0).

Makes account 9 a JPY account with opening balance 1,000,000 JPY (minor = 1000000, since JPY has
0 decimals) and base currency JPY for the budget hero. Scratch DB only. Run:
    cp /tmp/audit-C.sqlite /tmp/audit-C-jpy.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C-jpy.sqlite BUDGET_BASE_CURRENCY=JPY PYTHONPATH=. \
      uv run python docs/plans/quality-audit/repro/C/repro_jpy_display.py
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")

db = sqlite3.connect(URL.removeprefix("sqlite:///"))
db.execute("UPDATE accounts SET currency='JPY', opening_balance=1000000 WHERE id=9")
db.execute("DELETE FROM transactions WHERE (account_id=9 OR dest_account_id=9)")
db.commit()
db.close()

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.domain.money import format_money  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from tests.auth_support import login_cookie  # noqa: E402

settings = Settings()
app = create_app(settings)
name, value = login_cookie(settings)
print("correct rendering of the stored balance:", format_money(1_000_000, "JPY"))
with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
    c.cookies.set(name, value)
    today = c.get("/today").text
    accounts = c.get("/accounts").text
row = re.search(r"Cash Wallet.{0,400}?<span class=\"num[^\"]*\">([^<]+)</span>", today, re.S)
print("/today account row for the JPY account:", row.group(1) if row else "NOT FOUND")
m = re.findall(r"1[,.]?000[,.]?000(?:\.00)?|10[,.]?000\.00", accounts)
print("/accounts (money filter) mentions:", sorted(set(m)) or "none")
