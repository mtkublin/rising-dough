"""B-02: transit txn without destination persisted via UI route -> balance pages 500."""

from _web import USER_ID, fresh_conn, make_client

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts, categories

conn = fresh_conn()
acc = accounts.create(conn, USER_ID, NewAccount(name="V1-B02", currency="PLN", opening_balance=1000)).id
cat = categories.create(conn, USER_ID, NewCategory(name="V1-transit", direction=Direction.TRANSIT)).id
conn.commit()
c, _ = make_client()
for route in ("/accounts", "/today"):
    print("before", route, c.get(route).status_code)
r = c.post(
    "/transactions",
    data={"operation_date": "2026-11-19", "category_id": cat, "account_id": acc, "amount": "10", "dest_account_id": ""},
)
print("POST /transactions transit, empty dest ->", r.status_code)
n = conn.execute("select count(*) from transactions where category_id=? and dest_account_id is null", (cat,)).fetchone()[0]
print("persisted transit rows without destination:", n)
for route in ("/accounts", "/today", "/forecast"):
    print("after", route, c.get(route).status_code)
