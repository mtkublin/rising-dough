"""H2 formula chains: A references V's category ids in recurring formula terms on preview, create,
update; checks what is persisted and whether V's totals can leak through evaluation or views.

Run: uv run python docs/plans/quality-audit/repro/H2/h2_03_formula_foreign_sources.py | grep -v '^{"event"'
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import A, V, ex, fresh, login, q  # noqa: E402

s = fresh()
a = login(s, "A")
# V rule in V.cat_exp is 33.33/month (3333). A has own rule in A.cat_exp 33.33 too (for contrast).
ex("UPDATE recurring_rules SET default_amount=987654 WHERE id=?", (V["rule"],))  # V's distinctive amount 9876.54


def rule_form(src_ids, *, cat=None, name="A-formula"):  # noqa: ANN001, ANN201
    f = [
        ("cadence", "monthly"), ("start_date", "2026-01-01"), ("category_id", str(cat or A["cat_exp2"])),
        ("account_id", str(A["acc"])), ("default_amount", ""), ("default_description", name),
        ("day_of_month", "5"), ("amount_source", "formula"),
        ("terms[0][sign]", "+"), ("terms[0][coefficient_percent]", "100"),
    ]
    f += [("terms[0][source_category_ids]", str(i)) for i in src_ids]
    return f


print("== preview")
for label, ids in (("V's cat", [V["cat_exp"]]), ("nonexistent", [99999]), ("A's own", [A["cat_exp"]])):
    r = a.post("/recurring/formula/preview", [("terms[0][sign]", "+"), ("terms[0][coefficient_percent]", "100")] + [("terms[0][source_category_ids]", str(i)) for i in ids])
    print(f"  {label:12s} -> {r.status_code}  {'9876' in r.text=}  {r.text.strip()[:90]!r}")

print("== create with V's category as the only source")
before = q("select count(*) from recurring_rules where user_id=3")[0][0]
r = a.post("/recurring", rule_form([V["cat_exp"]]))
after = q("select id,default_amount,amount_formula from recurring_rules where user_id=3 order by id desc limit 1")
print("  status", r.status_code, "rules A:", before, "->", q("select count(*) from recurring_rules where user_id=3")[0][0])
print("  saved row:", after, "| V amount leaked in body:", "9876" in r.text or "987654" in r.text)

print("== create with V's + A's categories mixed")
r = a.post("/recurring", rule_form([V["cat_exp"], A["cat_exp"]], name="mixed"))
print("  status", r.status_code, q("select id,default_amount,amount_formula from recurring_rules where user_id=3 order by id desc limit 1"))

print("== create with nonexistent source id")
r = a.post("/recurring", rule_form([99999], name="ghost"))
print("  status", r.status_code, q("select id,default_amount,amount_formula from recurring_rules where user_id=3 order by id desc limit 1"))

print("== update A's rule to formula over V's category")
r = a.post(f"/recurring/{A['rule']}", rule_form([V["cat_exp"]], cat=A["cat_exp"], name="upd"))
print("  status", r.status_code, q("select id,default_amount,amount_formula from recurring_rules where id=?", (A["rule"],)))

print("== views that evaluate A's formulas: do they show V's 9876.54?")
for p in ("/ledger?view=recurring", "/today", "/plan?tab=budget", "/forecast", "/ledger?view=planned"):
    r = a.get(p)
    print(f"  GET {p:26s} -> {r.status_code} leak={'9876' in r.text or '9 876' in r.text or '987654' in r.text}")

print("== promote A's foreign-sourced formula rule")
rid = q("select id from recurring_rules where user_id=3 and default_description='A-formula'")
if rid:
    r = a.post(f"/recurring/{rid[0][0]}/promote", {"operation_date": "2026-11-12", "amount": "1.00", "description": "p"})
    print("  status", r.status_code)
print("  A transactions:", q("select id,amount,category_id,account_id from transactions where user_id=3"))
print("== any A rows referencing V parents:",
      q("select id from recurring_rules where user_id=3 and category_id in (select id from categories where user_id=2)"))
