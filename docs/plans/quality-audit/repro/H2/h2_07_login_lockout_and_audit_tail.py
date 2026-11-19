"""H2: (a) cross-user login lockout through the shared per-(IP,email) rate-limit bucket;
(b) admin /debug/audit-tail view of other users' rows (accepted by ADR-0078 §1, verifying the placeholder).

Run: uv run python docs/plans/quality-audit/repro/H2/h2_07_login_lockout_and_audit_tail.py | grep -v '^{"event"'
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PW, V, ex, fresh, login, q  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.web.app import create_app  # noqa: E402

s = fresh()
print("== (a) A (same IP as V) burns V's login bucket with wrong passwords")
cl = TestClient(create_app(s), base_url="https://testserver", follow_redirects=False)
cl.__enter__()
cl.get("/auth/login")
h = {"X-CSRF-Token": cl.cookies.get("__Host-csrf")}
for i in range(7):
    r = cl.post("/auth/login", data={"email": "v@x.test", "password": f"wrong-{i}"}, headers=h)
    print(f"  attempt {i + 1} wrong pw for v@x.test -> {r.status_code}")
r = cl.post("/auth/login", data={"email": "v@x.test", "password": PW}, headers=h)
print("  V with the CORRECT password, same IP ->", r.status_code, "Retry-After:", r.headers.get("retry-after"))
r = cl.post("/auth/login", data={"email": "a@x.test", "password": PW}, headers=h)
print("  A's own login, same IP (other email bucket) ->", r.status_code)
cl.__exit__(None, None, None)

print("== (b) admin audit-tail with V's rows")
s = fresh()
ex("UPDATE transactions SET description='VICTIMSECRET-live', amount=98765431 WHERE user_id=2")
v = login(s, "V")
v.post(f"/transactions/{V['txn']}", {"operation_date": "2026-11-12", "category_id": str(V["cat_exp"]), "account_id": str(V["acc"]), "amount": "55.55", "description": "VICTIMSECRET-edit"})
adm = login(s, "ADM")
r = adm.get("/debug/audit-tail", params={"n": "100"})
print("  status", r.status_code, "| V description in admin tail:", "VICTIMSECRET" in r.text, "| V amount:", "5555" in r.text or "55.55" in r.text)
print("  sample:", r.text[:300].replace("\n", " "))
