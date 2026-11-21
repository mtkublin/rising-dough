# Guard docstrings and teaching messages are prose; long lines are intentional.
"""INV-6: the currency exponent is applied everywhere (Q-029 exponent table, Q-011 renderer)."""

from __future__ import annotations

import re
import sqlite3

from fastapi.testclient import TestClient

from budget_planner.config import get_settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.money import ISO_4217_CURRENCIES, currency_decimals
from budget_planner.repositories import accounts as accounts_repo
from budget_planner.web.app import create_app
from tests.auth_support import login_cookie

ZERO = [
    "BIF",
    "CLP",
    "DJF",
    "GNF",
    "ISK",
    "JPY",
    "KMF",
    "KRW",
    "PYG",
    "RWF",
    "UGX",
    "VND",
    "VUV",
    "XAF",
    "XOF",
    "XPF",
]
THREE = ["BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"]
FRANKFURTER = {
    "AUD",
    "BGN",
    "BRL",
    "CAD",
    "CHF",
    "CNY",
    "CZK",
    "DKK",
    "EUR",
    "GBP",
    "HKD",
    "HUF",
    "IDR",
    "ILS",
    "INR",
    "ISK",
    "JPY",
    "KRW",
    "MXN",
    "MYR",
    "NOK",
    "NZD",
    "PHP",
    "PLN",
    "RON",
    "SEK",
    "SGD",
    "THB",
    "TRY",
    "USD",
    "ZAR",
}


def wrong_exponents() -> dict[str, tuple[int, int]]:
    return {
        c: (currency_decimals(c), want)
        for want, group in ((0, ZERO), (3, THREE))
        for c in group
        if c in ISO_4217_CURRENCIES and currency_decimals(c) != want
    }


def test_6a_exponent_table_matches_iso_4217() -> None:
    assert not wrong_exponents()


def test_6a_every_fx_reachable_code_has_the_right_exponent() -> None:
    assert not set(wrong_exponents()) & FRANKFURTER


def test_6b_today_shows_jpy_balance_without_decimals(seeded: sqlite3.Connection) -> None:
    # The net-worth card lists only the first 7 accounts: archive 7 demo accounts (scratch DB only).
    seeded.execute("UPDATE accounts SET deleted_at = '2026-11-01T00:00:00.000Z' WHERE id <= 7")
    accounts_repo.create(
        seeded, 1, NewAccount(name="Tokyo JPY", currency="JPY", opening_balance=12_345)
    )
    settings = get_settings()
    name, value = login_cookie(settings)
    client = TestClient(create_app(settings), cookies={name: value})
    html = client.get("/today").text
    match = re.search(r"Tokyo JPY.*?<span class=\"num[^>]*>([^<]*)</span>", html, re.S)
    assert match is not None
    assert match.group(1).strip() == "12,345"
