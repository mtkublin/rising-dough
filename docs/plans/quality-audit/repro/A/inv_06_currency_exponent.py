"""INV-6: currency exponent is applied everywhere (T-JPY class).

6a currency_decimals() vs ISO 4217 minor-unit exponents for the codes the app accepts.
6b real HTTP render of /today with a JPY account holding 12,345 JPY (stored 12345 minor):
   the Net-worth card must show 12,345 (money_num) not 123.45 (/100.0).
6c grep-style count of hard-coded '/ 100' in templates + python (static evidence).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import harness

conn = harness.fresh_db()

from budget_planner.domain.money import ISO_4217_CURRENCIES, currency_decimals  # noqa: E402

ZERO = "BIF CLP DJF GNF ISK JPY KMF KRW PYG RWF UGX VND VUV XAF XOF XPF".split()
THREE = "BHD IQD JOD KWD LYD OMR TND".split()
harness.banner("6a table vs ISO 4217 (codes in ISO_4217_CURRENCIES)")
wrong = {
    c: (currency_decimals(c), want)
    for want, group in ((0, ZERO), (3, THREE))
    for c in group
    if c in ISO_4217_CURRENCIES and currency_decimals(c) != want
}
print("code: (app, iso)", wrong)
frankfurter = set("AUD BGN BRL CAD CHF CNY CZK DKK EUR GBP HKD HUF IDR ILS INR ISK JPY KRW MXN MYR NOK NZD PHP PLN RON SEK SGD THB TRY USD ZAR".split())
reachable = sorted(set(wrong) & frankfurter)
harness.check("exponent table correct for all accepted ISO codes", not wrong, f"{len(wrong)} wrong")
harness.check("... and for every FX-reachable (frankfurter) code", not reachable, f"wrong+reachable={reachable}")

harness.banner("6b /today render with a JPY account")
from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import get_settings  # noqa: E402
from budget_planner.domain.accounts import NewAccount  # noqa: E402
from budget_planner.repositories import accounts as accounts_repo  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from tests.auth_support import login_cookie  # noqa: E402

# The net-worth card lists only the first 7 accounts: archive 7 demo accounts (scratch DB only)
# so the JPY account is inside the visible slice.
conn.execute("UPDATE accounts SET deleted_at = '2026-11-01T00:00:00.000Z' WHERE id <= 7")
accounts_repo.create(conn, 1, NewAccount(name="Tokyo JPY", currency="JPY", opening_balance=12_345))
settings = get_settings()
name, value = login_cookie(settings)
client = TestClient(create_app(settings), cookies={name: value})
html = client.get("/today").text
m = re.search(r"Tokyo JPY.*?<span class=\"num[^>]*>([^<]*)</span>", html, re.S)
print("Today net-worth card row for the JPY account renders:", m.group(1) if m else "NOT FOUND")
harness.check("JPY balance on /today shows 12,345", bool(m) and m.group(1).strip() == "12,345")
acc = client.get("/accounts").text
print("accounts page contains '12,345':", "12,345" in acc, "| contains '123.45':", "123.45" in acc)

harness.banner("6c hard-coded /100 occurrences (static)")
root = Path(harness.REPO_ROOT) / "src" / "budget_planner"
pat = re.compile(r"/ ?100(\.0)?\b|\* ?100\b")
tmpl = sum(len(pat.findall(p.read_text())) for p in (root / "web/templates").rglob("*.html"))
py = {
    str(p.relative_to(root)): len(pat.findall(p.read_text()))
    for p in root.rglob("*.py")
    if "web/" in str(p) or "services/" in str(p)
}
print("templates:", tmpl, "| python:", {k: v for k, v in py.items() if v})
