"""H2 undo/restore chains. V runs batch promote-due (planned + recurring); A replays V's undo payload
and crafted ids; also own-data stale-undo behaviour. Reports audit-row deltas and V row changes.

Run: uv run python docs/plans/quality-audit/repro/H2/h2_02_undo_chain.py | grep -v '^{"event"'
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import A, V, ex, fresh, login, q  # noqa: E402


def state(uid: int) -> dict:
    return {
        "txns": q("select id,deleted_at from transactions where user_id=? order by id", (uid,)),
        "planned": q("select id,promoted_to_txn_id,deleted_at from planned_transactions where user_id=? order by id", (uid,)),
        "rules": q("select id,next_due,last_promoted_date,active,deleted_at from recurring_rules where user_id=? order by id", (uid,)),
    }


def payload(resp) -> dict:  # noqa: ANN001
    return json.loads(resp.headers["HX-Trigger"])["toast"]["undo_payload"]


def csv(d: dict) -> dict:
    return {k: ",".join(map(str, v)) for k, v in d.items()}


s = fresh()
v, a = login(s, "V"), login(s, "A")
# V: batch promote planned + recurring
rp = v.post("/planned/batch/promote-due")
rr = v.post("/recurring/batch/promote-due")
print("V promote-due planned/recurring:", rp.status_code, rr.status_code)
pp, rp_ = payload(rp), payload(rr)
print("V payloads:", pp, rp_)
before_v, audit_before = state(2), q("select count(*) from audit_log")[0][0]
ex("INSERT INTO audit_log(entity_type,entity_id,operation,prev_json,new_json,user_id,actor_user_id) "
   "SELECT 'x',0,'update',NULL,NULL,2,2 WHERE 0")  # no-op (schema probe)
print("V state after promote:", before_v)

# A replays V's payloads verbatim
r1 = a.post("/planned/batch/undo", csv(pp))
r2 = a.post("/recurring/batch/undo", csv(rp_))
print("A replays V's planned undo ->", r1.status_code, "| recurring undo ->", r2.status_code)
print("V state unchanged by A's replay:", state(2) == before_v)
print("audit rows added by A's replay:", q("select count(*) from audit_log")[0][0] - audit_before)

# A crafts ids: V's txn/planned/rule + huge/negative/dup lists
for label, data in (
    ("negatives+dups", {"promoted_txn_ids": f"-1,0,{V['txn']},{V['txn']}", "promoted_planned_ids": f"-5,{V['pl']}"}),
    ("rule ids dup", {"promoted_txn_ids": "", "advanced_rule_ids": f"{V['rule']},{V['rule']}"}),
):
    path = "/planned/batch/undo" if "promoted_planned_ids" in data else "/recurring/batch/undo"
    r = a.post(path, data)
    print(f"A crafted {label:16s} -> {r.status_code}")
print("V state unchanged after crafted ids:", state(2) == before_v)

# ---- own-data: undo does NOT write an audit row for the next_due revert, and trusts latest audit row of ANY op
s = fresh()
v = login(s, "V")
rr = v.post("/recurring/batch/promote-due")
rule = V["rule"]
print("\nOWN-DATA recurring undo")
print(" after promote   :", q("select next_due,last_promoted_date from recurring_rules where id=?", (rule,)))
n0 = q("select count(*) from audit_log where entity_type='recurring_rule' and entity_id=?", (rule,))[0][0]
# user edits the rule description between promote and undo (stale Undo toast still on screen)
edit = {
    "cadence": "monthly", "start_date": "2026-01-01", "category_id": str(V["cat_exp"]), "account_id": str(V["acc"]),
    "default_amount": "33.33", "default_description": "edited-after-promote", "day_of_month": "5", "amount_source": "fixed",
}
print(" edit rule       :", v.post(f"/recurring/{rule}", edit).status_code)
print(" after edit      :", q("select next_due,last_promoted_date from recurring_rules where id=?", (rule,)))
u = v.post("/recurring/batch/undo", csv(payload(rr)))
print(" stale undo      :", u.status_code, q("select next_due,last_promoted_date from recurring_rules where id=?", (rule,)),
      "<== expected next_due back to 2026-11-05")
n1 = q("select count(*) from audit_log where entity_type='recurring_rule' and entity_id=?", (rule,))[0][0]
print(f" audit rows for rule: before-edit={n0} after-edit+undo={n1} (undo itself adds {n1 - n0 - 1})")

print("\nOWN-DATA planned undo after an edit (same stale-toast pattern)")
s = fresh()
v = login(s, "V")
rp = v.post("/planned/batch/promote-due")
pl = V["pl"]
print(" after promote  :", q("select promoted_to_txn_id from planned_transactions where id=?", (pl,)))
v.post(f"/planned/{pl}", {"operation_date": "2026-11-01", "category_id": str(V["cat_exp"]), "account_id": str(V["acc"]), "amount": "22.22", "description": "edited-after-promote"})
print(" after edit    :", q("select promoted_to_txn_id,description from planned_transactions where id=?", (pl,)))
u = v.post("/planned/batch/undo", csv(payload(rp)))
print(" stale undo    :", u.status_code, q("select promoted_to_txn_id from planned_transactions where id=?", (pl,)),
      "| promoted txn soft-deleted:", q("select deleted_at is not null from transactions where id=?", (payload(rp)["promoted_txn_ids"][0],)),
      "<== expected promoted_to_txn_id NULL")
