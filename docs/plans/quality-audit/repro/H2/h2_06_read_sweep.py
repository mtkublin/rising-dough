"""H2 read-side sweep: A's session across every GET route with V's ids/sentinel in every id-like or text
param (account_id, category_id, q, direction, page, page_size, period, include_deleted ...), plus
wildcard search, export routes, HTMX fragment headers. A leak = V sentinel/amount in the body.

Run: uv run python docs/plans/quality-audit/repro/H2/h2_06_read_sweep.py | grep -v '^{"event"'
"""

import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import A, V, ex, fresh, login, q  # noqa: E402

s = fresh()
# distinctive V values everywhere (live + soft-deleted), incl. a V transit pair
ex("UPDATE transactions SET amount=98765431, description='VICTIMSECRET-live' WHERE user_id=2")
ex("INSERT INTO transactions(user_id,operation_date,category_id,account_id,amount,description,deleted_at) "
   "VALUES (2,'2026-11-09',?,?,98765432,'VICTIMSECRET-deleted','2026-11-11T00:00:00.000Z')", (V["cat_exp"], V["acc"]))
ex("UPDATE planned_transactions SET amount=98765433, description='VICTIMSECRET-planned' WHERE user_id=2")
ex("UPDATE recurring_rules SET default_amount=98765434, default_description='VICTIMSECRET-rule' WHERE user_id=2")
ex("UPDATE accounts SET opening_balance=98765435 WHERE user_id=2")
# bare "VICTIMSECRET" is excluded: it is just the echoed q= search term
LEAK = ("VICTIMSECRET-", "987654", "9 876 54", "98765")

a = login(s, "A")
paths = [
    "/", "/today", "/today/upcoming", "/today/afford", "/add", "/accounts", "/accounts/last-checked", "/accounts/new",
    "/analytics", "/budget", "/budget/yearly", "/budget/manage", "/categories", "/forecast", "/forecast/view",
    "/ledger", "/ledger/table", "/ledger/recently-deleted", "/plan", "/plan/analytics", "/planned", "/planned/table",
    "/planned/export", "/planned/new", "/recurring", "/recurring/new", "/settings", "/settings/security",
    "/transactions", "/transactions/table", "/transactions/export", "/transactions/new", "/transactions/_limit_preview",
]
vals = {
    "account_id": [V["acc"], V["acc2"], f"{A['acc']},{V['acc']}", f"{V['acc']} OR 1=1", "-1"],
    "category_id": [V["cat_exp"], f"{V['cat_exp']},{A['cat_exp']}"],
    "q": ["VICTIMSECRET", "%", "_", "VICTIM%", "%' OR '1'='1"],
    "direction": ["expense", "income", "transit"],
    "view": ["actual", "planned", "recurring"],
    "tab": ["budget", "analytics", "categories", "fx", "prefs"],
    "period": ["month", "year", "all"],
    "page": ["1", "2", "0", "-1"], "page_size": ["500", "1", "0"],
    "include_deleted": ["1", "true"], "deleted": ["1"],
    "user_id": ["2"], "owner": ["2"], "date_from": ["2000-01-01"], "date_to": ["2100-01-01"],
    "amount": ["1"], "operation_date": ["2026-11-12"],
}
n = leaks = fivexx = 0
for p in paths:
    for key, vs in vals.items():
        for v in vs:
            for hx in (False, True):
                r = a.get(p, params={key: v}, headers={"HX-Request": "true"} if hx else {})
                n += 1
                if r.status_code >= 500:
                    fivexx += 1
                    print(f"  5xx {r.status_code} GET {p}?{key}={v}")
                body = r.text
                hit = [m for m in LEAK if m in body]
                if hit:
                    leaks += 1
                    print(f"  LEAK {hit} GET {p}?{key}={v} hx={hx}")
# combined filters
combo = {"account_id": V["acc"], "category_id": V["cat_exp"], "q": "VICTIMSECRET", "include_deleted": "1", "view": "actual"}
for p in ("/ledger", "/ledger/table", "/transactions/export", "/planned/export", "/ledger/recently-deleted"):
    r = a.get(p, params=combo)
    n += 1
    hit = [m for m in LEAK if m in r.text]
    print(f"combo GET {p:28s} -> {r.status_code} len={len(r.text)} leak={hit}")
    leaks += bool(hit)
print(f"requests={n} leaks={leaks} 5xx={fivexx}")
# control: V sees its own data on the same route (proves the sentinel is renderable)
v = login(s, "V")
r = v.get("/ledger", params={"q": "VICTIMSECRET"})
print("control: V's own ledger contains sentinel:", "VICTIMSECRET" in r.text)
