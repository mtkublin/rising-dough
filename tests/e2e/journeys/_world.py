"""Seeding and read-only DB access for the UI-map journeys (T-UT08b, ADR-0106).

Seeding goes through the app's own HTTP routes (the ``page`` fixture carries
the session and CSRF header), so no journey writes SQL. The DB handle is
opened read-only against the scratch database the ``live_server`` uses; it
must never point at the production database.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from tests.ui_map.locator import Locator, to_playwright

SqlParams = Sequence[Any]


def today() -> date:
    return datetime.now(tz=UTC).date()


def days_from_today(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


@dataclass(frozen=True)
class World:
    """A signed-in page plus seeding / read-only DB helpers."""

    page: Page
    base_url: str
    db_path: Path

    # --- navigation / lookups -------------------------------------------
    def goto(self, route: str) -> None:
        self.page.goto(f"{self.base_url}{route}")
        self.settle()

    def settle(self) -> None:
        """Wait for deferred scripts (htmx) so the next click is wired."""
        self.page.wait_for_load_state("networkidle")

    def find(self, loc: Locator) -> Any:
        return to_playwright(self.page, loc)

    # --- read-only DB ----------------------------------------------------
    def rows(self, sql: str, params: SqlParams = ()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, tuple(params)).fetchall()
        finally:
            conn.close()

    def write(self, sql: str, params: SqlParams = ()) -> None:
        """Seed the scratch DB directly where no route exists (FX cache only)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, tuple(params))
            conn.commit()
        finally:
            conn.close()

    def make_admin(self) -> None:
        """Promote the signed-in login user (scratch DB only; no route does this)."""
        self.write("UPDATE users SET is_admin = 1 WHERE id = 1")

    def wait_rows(
        self, sql: str, params: SqlParams = (), *, count: int = 1, timeout_s: float = 10.0
    ) -> list[sqlite3.Row]:
        """Poll until ``sql`` yields ``count`` rows (the UI write is asynchronous)."""
        deadline = time.monotonic() + timeout_s
        found = self.rows(sql, params)
        while len(found) != count and time.monotonic() < deadline:
            self.page.wait_for_timeout(100)
            found = self.rows(sql, params)
        assert len(found) == count, f"expected {count} rows for {sql!r}, got {len(found)}"
        return found

    def scalar(self, sql: str, params: SqlParams = ()) -> Any:
        found = self.rows(sql, params)
        assert found, f"no row for {sql!r} {tuple(params)!r}"
        return found[0][0]

    def audit_ops(self, entity_type: str, entity_id: int) -> list[str]:
        found = self.rows(
            "SELECT operation FROM audit_log WHERE entity_type = ? AND entity_id = ? ORDER BY id",
            (entity_type, entity_id),
        )
        return [r["operation"] for r in found]

    # --- seeding through the routes -------------------------------------
    def post(self, path: str, form: Mapping[str, str]) -> None:
        resp = self.page.request.post(
            f"{self.base_url}{path}", form=dict[str, str | float | bool](form)
        )
        assert resp.ok, f"POST {path} -> {resp.status}: {resp.text()[:300]}"

    def account(
        self,
        name: str = "Checking",
        *,
        opening: str = "500.00",
        currency: str = "PLN",
        liability: bool = False,
        credit_limit: str = "",
    ) -> int:
        form = {"name": name, "currency": currency, "opening_balance": opening}
        if liability:
            form["is_liability"] = "on"
            form["credit_limit"] = credit_limit
        self.post("/accounts", form)
        return int(self.scalar("SELECT id FROM accounts WHERE name = ?", (name,)))

    def category(self, name: str = "Groceries", direction: str = "expense") -> int:
        self.post("/categories", {"name": name, "direction": direction})
        return int(self.scalar("SELECT id FROM categories WHERE name = ?", (name,)))

    def transaction(
        self, account_id: int, category_id: int, amount: str, description: str, when: str = ""
    ) -> int:
        self.post(
            "/transactions",
            {
                "operation_date": when or today().isoformat(),
                "category_id": str(category_id),
                "account_id": str(account_id),
                "amount": amount,
                "description": description,
            },
        )
        return int(
            self.scalar(
                "SELECT id FROM transactions WHERE description = ? ORDER BY id DESC", (description,)
            )
        )

    def planned(
        self, account_id: int, category_id: int, amount: str, description: str, when: str = ""
    ) -> int:
        self.post(
            "/planned",
            {
                "operation_date": when or days_from_today(2),
                "category_id": str(category_id),
                "account_id": str(account_id),
                "amount": amount,
                "description": description,
            },
        )
        return int(
            self.scalar(
                "SELECT id FROM planned_transactions WHERE description = ? ORDER BY id DESC",
                (description,),
            )
        )

    def rule(
        self,
        account_id: int,
        category_id: int,
        amount: str,
        description: str,
        *,
        cadence: str = "monthly",
        start: str = "",
    ) -> int:
        self.post(
            "/recurring",
            {
                "cadence": cadence,
                "start_date": start or days_from_today(2),
                "category_id": str(category_id),
                "account_id": str(account_id),
                "default_amount": amount,
                "default_description": description,
            },
        )
        return int(
            self.scalar(
                "SELECT id FROM recurring_rules WHERE default_description = ? ORDER BY id DESC",
                (description,),
            )
        )
