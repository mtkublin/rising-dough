"""A-04: linked planned row + its recurring occurrence: budget dedups, forecast overlay helper does not."""

import datetime as dt

from _common import USER_ID, fresh_conn

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import accounts, categories, planned
from budget_planner.repositories import recurring as rec
from budget_planner.services import budget as budget_svc
from budget_planner.services import forecast

conn = fresh_conn()
today = dt.date(2026, 11, 19)
acc = accounts.create(conn, USER_ID, NewAccount(name="V1-A04", currency="PLN", opening_balance=0)).id
cat = categories.create(conn, USER_ID, NewCategory(name="V1-sub", direction=Direction.EXPENSE)).id
rule = rec.create_rule(
    conn, USER_ID,
    NewRecurringRule(cadence=Cadence.MONTHLY, start_date=dt.date(2026, 11, 25), category_id=cat, account_id=acc, default_amount=10_000),
)
# the linked, unpromoted planned row that represents the 2026-11-25 occurrence (as the app creates on edit-in-place)
planned.create(
    conn, USER_ID,
    NewPlannedTransaction(operation_date=dt.date(2026, 11, 25), category_id=cat, account_id=acc, amount=10_000,
                          recurring_rule_id=rule.id, occurrence_date=dt.date(2026, 11, 25)),
)
b = budget_svc._committed_by_category(conn, USER_ID, start=today, end=dt.date(2026, 12, 1), today=today)
f = forecast._committed_future_for_category(conn, USER_ID, cat, today + dt.timedelta(days=1), dt.date(2026, 11, 30), today=today)
print("budget committed for the item (dedups):", b.get(cat, 0))
print("forecast overlay helper committed       :", f)
