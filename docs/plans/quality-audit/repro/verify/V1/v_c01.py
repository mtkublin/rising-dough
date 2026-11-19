"""C-01: reconcile with an expense/income category: resulting balance vs target."""

from datetime import date

from _common import USER_ID, fresh_conn

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts, categories
from budget_planner.services import balance, reconciliation

conn = fresh_conn()
for tag, direction in (("expense", Direction.EXPENSE), ("income", Direction.INCOME)):
    for target in (150_000, 50_000):  # above / below derived 100_000
        acc = accounts.create(
            conn, USER_ID, NewAccount(name=f"V1-{tag}-{target}", currency="PLN", opening_balance=100_000)
        ).id
        cat = categories.create(
            conn, USER_ID, NewCategory(name=f"V1cat-{tag}-{target}", direction=direction)
        ).id
        reconciliation.reconcile(conn, USER_ID, acc, target, date(2026, 11, 19), category_id=cat)
        got = balance.derive_balance(conn, USER_ID, acc)
        print(f"{tag:8s} target={target} derived_after={got} {'OK' if got == target else 'MISMATCH'}")
