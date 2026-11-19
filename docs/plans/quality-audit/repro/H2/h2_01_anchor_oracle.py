"""H2-01: POST /budget/preferences/income-anchor is bound to user_id=1 (D-01) -> a non-owner user
(A, id 3) can (a) probe user 1's category ids/directions through distinct 200/422 answers and
(b) SET user 1's anchor to any of user 1's income categories, (c) clear it. A cannot set own anchor.

Run: uv run python docs/plans/quality-audit/repro/H2/h2_01_anchor_oracle.py 2>/dev/null
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import A, ADM, V, fresh, login, q, ex  # noqa: E402

s = fresh()
# give user 1 a second income category so a visible change is possible
ex("INSERT INTO categories(user_id,name,direction) VALUES (1,'ADM-salary2','income')")
new_inc = q("select max(id) from categories")[0][0]
a = login(s, "A")
print("user1 ids:", {"cat_inc": ADM["cat_inc"], "cat_exp": ADM["cat_exp"], "salary2": new_inc})
print("prefs before:", q("select user_id,value from user_preferences order by user_id"))
for label, cid in (
    ("user1 expense cat (oracle: direction leak)", ADM["cat_exp"]),
    ("user1 nonexistent id", 99999),
    ("A's OWN income cat (A cannot set own anchor)", A["cat_inc"]),
    ("V's income cat (not user 1's)", V["cat_inc"]),
    ("user1 income cat #2 (SETS user 1's pref)", new_inc),
):
    r = a.post("/budget/preferences/income-anchor", {"category_id": str(cid)})
    print(f"{label:48s} id={cid:<6} -> {r.status_code} {r.text[:70]!r}")
print("prefs after set:", q("select user_id,value from user_preferences order by user_id"))
r = a.post("/budget/preferences/income-anchor", {"category_id": ""})
print("A clears -> ", r.status_code, q("select user_id,value from user_preferences order by user_id"))
