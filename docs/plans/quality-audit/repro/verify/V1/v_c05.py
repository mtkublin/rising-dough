"""C-05: soft-delete an account that has a live recurring rule and balance."""

import datetime as dt

from _web import USER_ID, fresh_conn, make_client

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import accounts, categories
from budget_planner.repositories import recurring as rec

conn = fresh_conn()
acc = accounts.create(conn, USER_ID, NewAccount(name="V1-C05", currency="PLN", opening_balance=500_000)).id
cat = categories.create(conn, USER_ID, NewCategory(name="V1-rent", direction=Direction.EXPENSE)).id
rule = rec.create_rule(
    conn, USER_ID,
    NewRecurringRule(cadence=Cadence.MONTHLY, start_date=dt.date(2026, 11, 1), category_id=cat, account_id=acc, default_amount=10_000),
)
conn.commit()
c, _ = make_client()


def net() -> str:
    import re
    html = c.get("/accounts").text
    m = re.search(r'rd-accounts-hero__amount num">\s*([\-0-9,\.]+)', html)
    return m.group(1) if m else "?"


print("net worth before delete:", net())
r = c.post(f"/accounts/{acc}/delete")
print("delete ->", r.status_code, "(no confirmation / dependency check in route)")
print("net worth after delete :", net())
live = conn.execute("select count(*) from recurring_rules where account_id=? and active=1 and deleted_at is null", (acc,)).fetchone()[0]
print("live rules still pointing at deleted account:", live)
r = c.post(f"/recurring/{rule.id}/promote", data={})
print("promote rule on deleted account ->", r.status_code)
txns = conn.execute("select count(*) from transactions where account_id=?", (acc,)).fetchone()[0]
print("transactions created on deleted account:", txns)
for route in ("/today", "/forecast", "/ledger?view=recurring"):
    print(route, c.get(route).status_code)
