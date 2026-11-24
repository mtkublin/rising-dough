"""Base seed built from the designer handoff's data (T-UR00b, ADR-0147 §3).

The handoff (`docs/design/rising-dough-frontend/`) shows one coherent sample
world at the frozen date 2026-10-31: 10 accounts, 24 categories, a ledger, 3
planned items, recurring rules with formulas and overrides, a budget and 3
users. This module encodes those entities as frozen data (amounts in minor
units, from `docs/plans/ui-redesign/value-inventory.md` section 2 and the
handoff pages), then writes them into a fresh migrated scratch DB through the
repositories and services. Totals (net worth, left per day, spent, ...) are
never typed here: the app's services compute them from the entities.

State variants are named modifiers: pure `SeedData -> SeedData` functions
(`MODIFIER_NAMES`). Values the app cannot produce from this data (inconsistent
boards, counts of rows the handoff never lists, future-dated session times)
belong to `tests/visual/handoff_overlay.toml`, not here.

Only ever writes a fresh scratch file: it refuses a path that already exists.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.accounts import NewAccount, PatchAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory, PatchCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
)
from budget_planner.domain.snapshots import NewAccountSnapshot
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    sessions as sessions_repo,
    snapshots as snapshots_repo,
    transactions as transactions_repo,
    users as users_repo,
)
from budget_planner.services import (
    balance as balance_service,
    invites as invites_service,
    preferences as preferences_service,
)
from tests.auth_support import FAST_HASHER, TEST_PASSWORD, seed_login_user
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE

FROZEN_DAY: Final = dt.date.fromisoformat(HANDOFF_FIXTURE_DATE)
OWNER_ID: Final = 1
WARSAW_OFFSET: Final = dt.timedelta(hours=1)  # CET from 2026-10-25, so local = UTC + 1 h
INVITE_TOKEN: Final = "handoff-invite-accountant"  # noqa: S105  # pragma: allowlist secret  # fixed link token of the scratch DB
OWNER_USER_AGENT: Final = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0"
)
SAFARI_USER_AGENT: Final = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)


def _local(day: str, hhmm: str) -> dt.datetime:
    """A Warsaw wall-clock instant (CET, after 2026-10-25) as aware UTC."""
    local = dt.datetime.fromisoformat(f"{day}T{hhmm}:00")
    return (local - WARSAW_OFFSET).replace(tzinfo=dt.UTC)


@dataclass(frozen=True, slots=True)
class AccountSeed:
    name: str
    type: str
    balance_minor: int  # target balance shown on the handoff Accounts page
    checked: tuple[str, ...]  # snapshot dates (ISO), the last one is "checked"
    credit_limit_minor: int | None = None
    is_liability: bool = False


@dataclass(frozen=True, slots=True)
class CategorySeed:
    name: str
    direction: Direction
    color: str | None  # None = "default colour" on the Settings page


@dataclass(frozen=True, slots=True)
class TxnSeed:
    day: str
    category: str
    account: str
    amount_minor: int  # positive; reconciliation rows carry their sign
    description: str
    dest_account: str | None = None


@dataclass(frozen=True, slots=True)
class PlannedSeed:
    day: str
    category: str
    account: str
    amount_minor: int
    description: str
    deleted_at: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class RuleSeed:
    cadence: Cadence
    next_due: str
    category: str
    account: str
    amount_minor: int
    description: str
    start: str | None = None  # earlier start when overrides precede next_due
    end: str | None = None
    dest_account: str | None = None
    formula: bool = False


@dataclass(frozen=True, slots=True)
class OverrideSeed:
    rule_description: str
    rule_next_due: str  # identifies the rule among same-described ones
    occurrence: str
    amount_minor: int


@dataclass(frozen=True, slots=True)
class BudgetSeed:
    category: str
    amount_minor: int


@dataclass(frozen=True, slots=True)
class UserSeed:
    email: str
    name: str
    is_admin: bool
    must_change_password: bool
    last_seen: dt.datetime | None  # a session is created at that instant


@dataclass(frozen=True, slots=True)
class SeedData:
    accounts: tuple[AccountSeed, ...]
    categories: tuple[CategorySeed, ...]
    deleted_categories: tuple[tuple[CategorySeed, dt.datetime], ...]
    transactions: tuple[TxnSeed, ...]
    planned: tuple[PlannedSeed, ...]
    rules: tuple[RuleSeed, ...]
    overrides: tuple[OverrideSeed, ...]
    budgets: tuple[BudgetSeed, ...]
    users: tuple[UserSeed, ...]
    income_anchor: str
    invite_email: str | None
    invite_age_days: int


# value-inventory 2.2 (balances in PLN as the handoff prints them; the two EUR-named
# accounts show PLN figures there, so the seed keeps every account in the base currency).
ACCOUNTS: Final[tuple[AccountSeed, ...]] = (
    AccountSeed("Investments A", "investment", 1_699_129, ("2026-04-01",)),
    AccountSeed("Savings", "savings", 1_245_304, ("2026-04-01",)),
    AccountSeed("Investments C", "investment", 572_922, ("2026-07-01",)),
    AccountSeed("Checking", "bank", 368_581, ("2026-03-01", "2026-04-01")),
    AccountSeed("Investments B", "investment", 238_368, ("2026-04-01",)),
    AccountSeed("Investments D", "investment", 228_746, ("2026-07-01",)),
    AccountSeed("Cash Wallet", "cash", 8_594, ("2026-04-01",)),
    AccountSeed("Checking EUR", "bank", -660_115, ("2026-07-01",)),
    AccountSeed(
        "Credit Card",
        "credit_card",
        -245_574,
        ("2026-04-01",),
        credit_limit_minor=1_497_737,
        is_liability=True,
    ),
    AccountSeed("Everyday Spending", "bank", -11_986, ("2026-09-01",)),
)

_EXPENSE_COLORS: Final = (
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#3b82f6",
    "#8b5cf6",
    "#ec4899",
)
_EXPENSE_NAMES: Final = (
    "Bank Fees #18",
    "Big Purchases",
    "Car",
    "Entertainment",
    "Fixed costs",
    "Gifts",
    "Groceries",
    "Health & Beauty",
    "Nights Out",
    "Opłaty bankowe i prowizje",
    "Other",
    "Sport & Hobby",
    "Subscriptions",
    "Takeaway",
    "Taxes",
    "Transport",
    "Travel",
)
_INCOME_NAMES: Final = ("Interest", "Profit Share", "Salary", "Side Income", "VAT Refund")
_DEFAULT_COLOUR: Final = frozenset({"Opłaty bankowe i prowizje", "Interest", "Profit Share"})


def _categories() -> tuple[CategorySeed, ...]:
    out: list[CategorySeed] = []
    for names, direction in (
        (_EXPENSE_NAMES, Direction.EXPENSE),
        (_INCOME_NAMES, Direction.INCOME),
    ):
        for i, name in enumerate(names):
            color = None if name in _DEFAULT_COLOUR else _EXPENSE_COLORS[i % len(_EXPENSE_COLORS)]
            out.append(CategorySeed(name, direction, color))
    return tuple(out)


CATEGORIES: Final = _categories()
SYSTEM_CATEGORY_COLORS: Final = {"Reconciliation": "#64748b", "Transit": "#0ea5e9"}

# Budget lines (value-inventory 2.4 budget): default tier per category.
BUDGETS: Final[tuple[BudgetSeed, ...]] = (
    BudgetSeed("Big Purchases", 60_435),
    BudgetSeed("Car", 35_416),
    BudgetSeed("Entertainment", 19_086),
    BudgetSeed("Gifts", 34_634),
    BudgetSeed("Groceries", 95_674),
    BudgetSeed("Health & Beauty", 37_937),
    BudgetSeed("Nights Out", 78_311),
    BudgetSeed("Other", 34_461),
    BudgetSeed("Sport & Hobby", 31_918),
    BudgetSeed("Subscriptions", 59_257),
    BudgetSeed("Takeaway", 39_427),
    BudgetSeed("Transport", 15_547),
    BudgetSeed("Travel", 102_805),
)

# Spent this period per budgeted category (handoff budget page), minus the rows the
# ledger lists explicitly; the rest is one lump entry per category.
_SPENT: Final = {
    "Big Purchases": 23_482,
    "Car": 35_935,
    "Entertainment": 26_533,
    "Groceries": 42_717,
    "Health & Beauty": 41_411,
    "Nights Out": 160_037,
    "Other": 24_504,
    "Sport & Hobby": 1_744,
    "Subscriptions": 53_301,
    "Takeaway": 66_704,
    "Transport": 22_090,
    "Travel": 2_997,
}

# Actual ledger rows listed on the handoff (7 to 31 October 2026).
_LISTED: Final[tuple[TxnSeed, ...]] = (
    TxnSeed("2026-10-31", "Takeaway", "Credit Card", 3_550, "Takeaway"),
    TxnSeed("2026-10-30", "Nights Out", "Credit Card", 6_312, "Nights Out"),
    TxnSeed("2026-10-30", "Big Purchases", "Credit Card", 4_896, "Big Purchases"),
    TxnSeed("2026-10-30", "Takeaway", "Credit Card", 10_509, "Takeaway"),
    TxnSeed("2026-10-30", "Groceries", "Credit Card", 741, "Zakupy spożywcze · Żabka"),
    TxnSeed("2026-10-30", "Entertainment", "Checking", 2_369, "Entertainment"),
    TxnSeed("2026-10-29", "Reconciliation", "Cash Wallet", -1_472, "Reconciliation"),
    TxnSeed("2026-10-29", "Reconciliation", "Investments C", 957, "Reconciliation"),
    TxnSeed("2026-10-29", "Health & Beauty", "Credit Card", 13_496, "Health & Beauty"),
    TxnSeed("2026-10-26", "Side Income", "Checking", 2_096, "Side Income"),
    TxnSeed("2026-10-26", "Transit", "Checking", 2_193, "Transit", "Credit Card"),
)


def _lumps() -> tuple[TxnSeed, ...]:
    listed: dict[str, int] = {}
    for t in _LISTED:
        if t.category in _SPENT:
            listed[t.category] = listed.get(t.category, 0) + t.amount_minor
    lumps = [
        TxnSeed("2026-10-12", cat, "Checking", total - listed.get(cat, 0), cat)
        for cat, total in _SPENT.items()
        if total - listed.get(cat, 0) > 0
    ]
    # Unbudgeted categories (budget page): spent but no budget line.
    lumps.append(TxnSeed("2026-10-10", "Fixed costs", "Checking", 579_081, "Fixed costs"))
    lumps.append(TxnSeed("2026-10-10", "Taxes", "Checking", 861_182, "Taxes"))
    # The income anchor's last payday opens the fiscal period (7 Oct to 7 Nov).
    lumps.append(TxnSeed("2026-10-07", "Salary", "Checking EUR", 1_580_000, "Salary"))
    return tuple(lumps)


TRANSACTIONS: Final = (*_LISTED, *_lumps())

PLANNED: Final[tuple[PlannedSeed, ...]] = (
    PlannedSeed("2026-12-15", "Car", "Checking", 223_980, "Car"),
    PlannedSeed("2026-10-28", "Other", "Checking", 41_200, "Annual insurance"),
    PlannedSeed("2026-10-31", "VAT Refund", "Checking EUR", 112_045, "Tax refund"),
    PlannedSeed("2026-12-15", "Car", "Checking", 230_635, "Car", _local("2026-10-29", "20:30")),
)

M, Q, Y = Cadence.MONTHLY, Cadence.QUARTERLY, Cadence.YEARLY
RULES: Final[tuple[RuleSeed, ...]] = (
    RuleSeed(M, "2026-11-01", "Fixed costs", "Credit Card", 27_794, "Fixed Costs"),
    RuleSeed(M, "2026-11-01", "Subscriptions", "Credit Card", 1_131, "Subscriptions"),
    RuleSeed(M, "2026-11-05", "Subscriptions", "Checking", 2_329, "Subscriptions"),
    RuleSeed(M, "2026-11-07", "VAT Refund", "Checking EUR", 372_921, "VAT Refund", formula=True),
    RuleSeed(M, "2026-11-07", "Salary", "Checking EUR", 1_621_397, "Salary", start="2026-07-07"),
    RuleSeed(M, "2026-11-07", "Fixed costs", "Checking", 52_218, "Fixed Costs"),
    RuleSeed(M, "2026-11-07", "Fixed costs", "Checking", 229_687, "Fixed Costs"),
    RuleSeed(M, "2026-11-07", "Bank Fees #18", "Checking EUR", 1_556, "Bank Fees #18"),
    RuleSeed(
        M,
        "2026-11-12",
        "Taxes",
        "Checking EUR",
        183_693,
        "Taxes",
        start="2026-10-12",
        formula=True,
    ),
    RuleSeed(
        M,
        "2026-11-12",
        "Transit",
        "Checking EUR",
        1_241_580,
        "Transit",
        dest_account="Investments C",
        formula=True,
    ),
    RuleSeed(M, "2026-11-15", "Fixed costs", "Checking", 212_639, "Fixed Costs", end="2028-05-15"),
    RuleSeed(M, "2026-11-18", "Fixed costs", "Checking", 190_000, "Rent", start="2026-02-18"),
    RuleSeed(Q, "2027-01-15", "Car", "Checking", 41_200, "Car insurance"),
    RuleSeed(Y, "2027-03-07", "Salary", "Checking EUR", 3_053_619, "Salary", formula=True),
    RuleSeed(Y, "2027-03-10", "Car", "Checking", 405_682, "Car"),
)

OVERRIDES: Final[tuple[OverrideSeed, ...]] = (
    OverrideSeed("Salary", "2026-11-07", "2026-10-07", 1_580_000),
    OverrideSeed("Salary", "2026-11-07", "2026-09-07", 1_610_000),
    OverrideSeed("Salary", "2026-11-07", "2026-08-07", 1_650_000),
    OverrideSeed("Salary", "2026-11-07", "2026-07-07", 1_595_000),
    OverrideSeed("Taxes", "2026-11-12", "2026-10-12", 164_000),
    OverrideSeed("Rent", "2026-11-18", "2027-02-18", 195_000),
    OverrideSeed("Rent", "2026-11-18", "2027-03-18", 195_000),
)

USERS: Final[tuple[UserSeed, ...]] = (
    UserSeed("partner@example.test", "Ola", False, False, _local("2026-10-30", "21:12")),
    UserSeed("parent@example.test", "Ewa", False, True, None),
)

BASE: Final = SeedData(
    accounts=ACCOUNTS,
    categories=CATEGORIES,
    deleted_categories=(
        (CategorySeed("VAT Refund #6", Direction.INCOME, "#a855f7"), _local("2026-10-29", "20:06")),
        (CategorySeed("Bank Fees", Direction.EXPENSE, "#f43f5e"), _local("2026-10-28", "11:03")),
        (
            CategorySeed("Opłaty bankowe i prowizje", Direction.EXPENSE, None),
            _local("2026-10-28", "10:58"),
        ),
    ),
    transactions=TRANSACTIONS,
    planned=PLANNED,
    rules=RULES,
    overrides=OVERRIDES,
    budgets=BUDGETS,
    users=USERS,
    income_anchor="Salary",
    invite_email="accountant@example.test",
    invite_age_days=0,
)

LONG_DESCRIPTION: Final = (
    "Quarterly reimbursement for the shared apartment renovation, including the "
    "contractor invoice, materials and the delivery surcharge agreed in September"
)


def _empty_ledger(d: SeedData) -> SeedData:
    return replace(d, transactions=())


def _empty_planned(d: SeedData) -> SeedData:
    return replace(d, planned=tuple(p for p in d.planned if p.deleted_at is not None))


def _empty_recurring(d: SeedData) -> SeedData:
    return replace(d, rules=(), overrides=())


def _empty_accounts(d: SeedData) -> SeedData:
    return replace(_empty_ledger(_empty_recurring(d)), planned=(), accounts=())


def _empty(d: SeedData) -> SeedData:
    """Today `--empty`: no accounts, ledger, planned or recurring; budgets stay."""
    return _empty_accounts(d)


def _long(d: SeedData) -> SeedData:
    stress = (
        TxnSeed("2026-10-31", "Big Purchases", "Checking", 123_456_789, LONG_DESCRIPTION),
        TxnSeed("2026-10-31", "Salary", "Checking", 123_456_789, LONG_DESCRIPTION),
    )
    return replace(d, transactions=(*stress, *d.transactions))


def _invite_expired(d: SeedData) -> SeedData:
    return replace(d, invite_age_days=8)


def _no_data_change(d: SeedData) -> SeedData:
    return d


# (name, transformation, what it models). `no-matches` and `over-limit` are request
# states: the filter query / entry amount alone produce them, the data stays the base.
_MODIFIERS: Final = (
    ("empty", _empty, "Today --empty: no accounts, ledger, planned, recurring"),
    ("empty-accounts", _empty_accounts, "Accounts --empty (also empties the rest)"),
    ("empty-ledger", _empty_ledger, "Ledger actual --empty: no transactions"),
    ("empty-planned", _empty_planned, "Ledger planned --empty: no live planned items"),
    ("empty-recurring", _empty_recurring, "Ledger recurring --empty: no rules"),
    ("long", _long, "Ledger actual --long: 1,234,567.89 amounts, long descriptions"),
    ("no-matches", _no_data_change, "query state: filters matching nothing, data unchanged"),
    (
        "over-limit",
        _no_data_change,
        "query state: a 13,000.00 entry exceeds Credit Card's 12,521.63 left",
    ),
    ("invite-expired", _invite_expired, "invite page --expired: link older than 7 days"),
    ("form-error", _no_data_change, "request states (422, wrong password): no data change"),
)
MODIFIER_NAMES: Final = tuple(name for name, _, _ in _MODIFIERS)


def apply_modifiers(base: SeedData, modifiers: Iterable[str]) -> SeedData:
    """Fold the named modifiers over ``base`` (pure; unknown names raise)."""
    data = base
    for name in modifiers:
        for known, fn, _ in _MODIFIERS:
            if known == name:
                data = fn(data)
                break
        else:
            raise ValueError(f"unknown seed modifier {name!r}; known: {MODIFIER_NAMES}")
    return data


@dataclass(frozen=True, slots=True)
class SeedResult:
    """What a build leaves behind for the server fixture."""

    db_path: Path
    session_token: str
    invite_token: str | None


def _at(day: str, hour: int = 9) -> dt.datetime:
    return dt.datetime.fromisoformat(f"{day}T{hour:02d}:00:00").replace(tzinfo=dt.UTC)


def _write_accounts(conn: sqlite3.Connection, data: SeedData) -> dict[str, int]:
    ids: dict[str, int] = {}
    for a in data.accounts:
        row = accounts_repo.create(
            conn,
            OWNER_ID,
            NewAccount(
                name=a.name,
                currency="PLN",
                type=a.type,
                is_liability=a.is_liability,
                credit_limit_minor=a.credit_limit_minor,
            ),
        )
        ids[a.name] = row.id
    return ids


def _write_categories(conn: sqlite3.Connection, data: SeedData) -> dict[str, int]:
    ids: dict[str, int] = {c.name: c.id for c in categories_repo.list_all(conn, OWNER_ID)}
    for name, color in SYSTEM_CATEGORY_COLORS.items():
        categories_repo.update(conn, OWNER_ID, ids[name], PatchCategory(color=color))
    for seed, deleted_at in data.deleted_categories:
        row = categories_repo.create(
            conn, OWNER_ID, NewCategory(name=seed.name, direction=seed.direction, color=seed.color)
        )
        with clock.frozen(deleted_at):
            categories_repo.soft_delete(conn, OWNER_ID, row.id)
    for seed in data.categories:
        row = categories_repo.create(
            conn, OWNER_ID, NewCategory(name=seed.name, direction=seed.direction, color=seed.color)
        )
        ids[seed.name] = row.id
    return ids


def _write_rules(
    conn: sqlite3.Connection, data: SeedData, acc: dict[str, int], cat: dict[str, int]
) -> None:
    formula = AmountFormula(
        terms=(
            FormulaTerm(
                sign="+",
                coefficient_bps=1900,
                source_category_ids=(cat["Salary"], cat["Side Income"]),
            ),
            FormulaTerm(
                sign="-", coefficient_bps=1900, source_category_ids=(cat["Bank Fees #18"],)
            ),
        )
    )
    rule_ids: dict[tuple[str, str], int] = {}
    for r in data.rules:
        due = dt.date.fromisoformat(r.next_due)
        rule = recurring_repo.create_rule(
            conn,
            OWNER_ID,
            NewRecurringRule(
                cadence=r.cadence,
                start_date=dt.date.fromisoformat(r.start) if r.start else due,
                end_date=dt.date.fromisoformat(r.end) if r.end else None,
                category_id=cat[r.category],
                account_id=acc[r.account],
                dest_account_id=acc[r.dest_account] if r.dest_account else None,
                default_amount=r.amount_minor,
                default_description=r.description,
                day_of_month=due.day,
                month_of_year=due.month if r.cadence is not Cadence.MONTHLY else None,
                amount_formula=formula if r.formula else None,
            ),
        )
        recurring_repo.update_rule(conn, OWNER_ID, rule.id, PatchRecurringRule(next_due=due))
        rule_ids[(r.description, r.next_due)] = rule.id
    for o in data.overrides:
        recurring_repo.upsert_override(
            conn,
            OWNER_ID,
            NewRecurringOverride(
                rule_id=rule_ids[(o.rule_description, o.rule_next_due)],
                occurrence_date=dt.date.fromisoformat(o.occurrence),
                state=OverrideState.OVERRIDDEN,
                amount_override=o.amount_minor,
            ),
        )


def _write_entries(
    conn: sqlite3.Connection, data: SeedData, acc: dict[str, int], cat: dict[str, int]
) -> None:
    for t in data.transactions:
        transactions_repo.create(
            conn,
            OWNER_ID,
            NewTransaction(
                operation_date=dt.date.fromisoformat(t.day),
                category_id=cat[t.category],
                account_id=acc[t.account],
                amount=t.amount_minor,
                description=t.description,
                dest_account_id=acc[t.dest_account] if t.dest_account else None,
            ),
        )
    for p in data.planned:
        row = planned_repo.create(
            conn,
            OWNER_ID,
            NewPlannedTransaction(
                operation_date=dt.date.fromisoformat(p.day),
                category_id=cat[p.category],
                account_id=acc[p.account],
                amount=p.amount_minor,
                description=p.description,
            ),
        )
        if p.deleted_at is not None:
            with clock.frozen(p.deleted_at):
                planned_repo.soft_delete(conn, OWNER_ID, row.id)
    for b in data.budgets:
        budgets_repo.set_default(
            conn, OWNER_ID, NewBudgetDefault(category_id=cat[b.category], amount=b.amount_minor)
        )


def _fit_balances(conn: sqlite3.Connection, data: SeedData, acc: dict[str, int]) -> None:
    """Set each opening balance so the derived balance equals the handoff's figure."""
    rows = accounts_repo.list_all(conn, OWNER_ID)
    derived = balance_service.derive_balances(conn, OWNER_ID, rows)
    for a in data.accounts:
        accounts_repo.update(
            conn,
            OWNER_ID,
            acc[a.name],
            PatchAccount(opening_balance=a.balance_minor - derived[acc[a.name]]),
        )
        for day in a.checked:
            snapshots_repo.create(
                conn, OWNER_ID, NewAccountSnapshot(account_id=acc[a.name], balance=a.balance_minor)
            )
            conn.execute(
                "UPDATE account_snapshots SET taken_at = ? "
                "WHERE id = (SELECT max(id) FROM account_snapshots)",
                (f"{day}T09:00:00.000Z",),
            )
    conn.commit()


def _write_users(conn: sqlite3.Connection, data: SeedData) -> str | None:
    for u in data.users:
        user = users_repo.create_user(
            conn,
            data=users_repo.NewUser(
                name=u.name,
                email=u.email,
                password_hash=FAST_HASHER.hash(TEST_PASSWORD),
                is_admin=u.is_admin,
                must_change_password=u.must_change_password,
            ),
        )
        if u.last_seen is not None:
            sessions_repo.create_session(
                conn, user.id, ip="83.24.117.30", user_agent=SAFARI_USER_AGENT, now=u.last_seen
            )
    if data.invite_email is None:
        return None
    created = _at(FROZEN_DAY.isoformat(), 10) - dt.timedelta(days=data.invite_age_days)
    invites_service.create_invite(
        conn,
        OWNER_ID,
        email=data.invite_email,
        is_admin=False,
        tokens=_FixedToken(INVITE_TOKEN),
        now=created,
    )
    return INVITE_TOKEN


@dataclass(frozen=True, slots=True)
class _FixedToken:
    value: str

    def new_token(self, nbytes: int) -> str:
        return self.value


def build_seed(db_path: Path, *, modifiers: Iterable[str] = ()) -> SeedResult:
    """Migrate a fresh scratch DB at ``db_path`` and write the handoff world into it.

    ``db_path`` must not exist yet (the builder never reuses or edits an existing DB).
    """
    if db_path.exists():
        raise FileExistsError(f"{db_path} exists; the seed builds fresh scratch DBs only")
    data = apply_modifiers(BASE, modifiers)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}")
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        seed_login_user(conn)
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (OWNER_ID,))
        conn.commit()
        frozen_now = _at(FROZEN_DAY.isoformat(), 10)
        with clock.frozen(frozen_now):
            acc = _write_accounts(conn, data)
            cat = _write_categories(conn, data)
            _write_entries(conn, data, acc, cat)
            _write_rules(conn, data, acc, cat)
            _fit_balances(conn, data, acc)
            preferences_service.set_income_anchor_category_id(
                conn, OWNER_ID, cat[data.income_anchor]
            )
            invite_token = _write_users(conn, data)
            session = sessions_repo.create_session(
                conn, OWNER_ID, ip="83.24.117.9", user_agent=OWNER_USER_AGENT, now=frozen_now
            )
    finally:
        conn.close()
    return SeedResult(db_path=db_path, session_token=session.token, invite_token=invite_token)
