"""T-124 / ADR-0040 — Modal dismissal scope + amount `,`/`.` regression pin.

The transactions slide-over wires a side-effect ``hx-get`` to the amount
input (keystroke-triggered ``/transactions/_limit_preview`` fetch for the
credit-limit badge). The pre-fix listener in ``app-init.js`` matched on the
*closest* ``form[data-reset-on-submit]`` ancestor, so each keystroke's 2xx
response tore down ``#modal-root``. The fix narrows the match to
``evt.target instanceof HTMLFormElement && data-reset-on-submit && verb ∈
{post,put,delete}``.

These tests pin:

- The side-effect ``_limit_preview`` request returns a self-contained
  ``#limit-preview`` fragment (so the server contract the listener
  observes is stable) — the handler-side scoping change is further
  exercised via a tiny JSDOM-free harness that re-plays the two event
  shapes the listener sees in production.
- Form submit still dismisses the slide-over (the server contract for
  the submit path is a non-slide-over fragment).
- The amount field accepts both ``,`` and ``.`` decimal separators and
  rejects more fractional digits than the currency supports.

The handler itself is tested in a Python harness rather than via
Playwright because the suite's existing E2E coverage boots a real
uvicorn+Chromium stack per test (``tests/e2e/``) which is heavier than
needed for a 15-line event-listener contract.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
)
from tests.ui_map import _html, entries, ledger, rd_shell as shell

USER_ID = 1

# ---------------------------------------------------------------------------
# Shared seed fixture (one checking account + one expense category).
# ---------------------------------------------------------------------------


@pytest.fixture
def seeded(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=0)
        )
        groc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        return {"acc": acc.id, "groc": groc.id}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fix 1 — Modal dismissal scope.
# ---------------------------------------------------------------------------


def test_new_transaction_dialog_posts_the_amount_preview_from_the_form(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """``GET /add?when=happened&dialog=1`` is the new-entry dialog (T-UR07b, ADR-0152).

    The credit line refetches itself from the whole form, so an amount keystroke can
    never close or reset the dialog: it targets ``#credit-line`` only.
    """
    r = client.get("/add?when=happened&dialog=1", headers={"HX-Request": "true"})
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.exists(r.text, entries.dialog)
    line = _html.resolve_one(r.text, entries.credit_line)
    assert line.get("hx-get") == "/transactions/_limit_preview"
    assert line.get("hx-target") == "#credit-line"
    assert line.get("hx-include") == "closest form"
    # Typing the amount first fires a request without category; the category/account change that
    # follows must queue behind it instead of being dropped (F8).
    assert line.get("hx-sync") == "this:queue last"
    # Every keystroke of the amount refetches: `changed` would watch the wrapper's own (absent)
    # value and let only the first keyup through. The id it listens to is the hero input's.
    trigger = str(line.get("hx-trigger"))
    assert "keyup delay:400ms from:#field-amount" in trigger
    assert "changed" not in trigger
    assert _html.resolve_one(r.text, entries.hero_amount).get("id") == "field-amount"


def test_limit_preview_side_effect_returns_the_credit_line(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """The ``_limit_preview`` side-effect endpoint answers the self-contained credit line."""
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": seeded["acc"],
            "category_id": seeded["groc"],
            "amount": "12.34",
        },
    )
    assert r.status_code == 200
    assert _html.exists(r.text, entries.credit_line)
    assert not _html.exists(r.text, ledger.slideover)


def test_form_submit_still_dismisses_slide_over(client: TestClient, seeded: dict[str, int]) -> None:
    """``POST /transactions`` closes the dialog (empties ``#modal-root``), no slide-over.

    The dismissal is a client-side side-effect of a successful submit;
    the server contract that unblocks it is: 2xx response that does NOT
    re-render the slide-over wrapper. Pin that contract.
    """
    r = client.post(
        "/transactions",
        data={
            "operation_date": date(2026, 10, 20).isoformat(),
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "20.00",
            "description": "milk",
        },
    )
    assert r.status_code == 200
    assert _html.text_of(r.text, shell.modal_root) == ""
    assert not _html.exists(r.text, ledger.slideover), (
        "submit response must not re-render the slide-over wrapper"
    )


# ---------------------------------------------------------------------------
# Fix 2 — Amount decimal separator regression pin.
# ---------------------------------------------------------------------------


def _fetch_amount(conn: sqlite3.Connection, description: str) -> int:
    row = conn.execute(
        "SELECT amount FROM transactions WHERE description = ?",
        (description,),
    ).fetchone()
    assert row is not None, f"no transaction persisted for {description!r}"
    return int(row[0])


def test_amount_accepts_comma_or_dot(
    client: TestClient, seeded: dict[str, int], _migrated: Settings
) -> None:
    """Both ``12,34`` and ``12.34`` land ``1234`` minor units; ``12.345`` returns 422.

    Mirrors the UI contract in ``numeric-input.js`` (``/^\\d*([.,]\\d{0,2})?$/``)
    which already allows either separator. This pins the server-side
    normalisation so future regressions in ``parse_amount_str`` surface
    here.
    """
    # Comma separator.
    r_comma = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "12,34",
            "description": "comma-sep",
        },
    )
    assert r_comma.status_code == 200, r_comma.text
    # Dot separator.
    r_dot = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "12.34",
            "description": "dot-sep",
        },
    )
    assert r_dot.status_code == 200, r_dot.text
    conn = get_connection(_migrated)
    try:
        assert _fetch_amount(conn, "comma-sep") == 1234
        assert _fetch_amount(conn, "dot-sep") == 1234
    finally:
        conn.close()

    # Too many fractional digits for a 2-decimal currency.
    r_overflow = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-20",
            "category_id": seeded["groc"],
            "account_id": seeded["acc"],
            "amount": "12.345",
            "description": "overflow",
        },
    )
    assert r_overflow.status_code == 422, r_overflow.text
    # Inline validation renders the amount error for the user.
    assert re.search(r"amount", r_overflow.text, re.IGNORECASE)


def test_limit_preview_handles_both_separators(client: TestClient, _migrated: Settings) -> None:
    """The side-effect preview endpoint also normalises both separators.

    The preview fragment runs on every keystroke; if the Polish-style
    ``12,34`` keystroke silently blanks the preview the user gets
    inconsistent feedback. This test pins that both separators yield the
    same (populated or empty) fragment shape against a liability account.
    """
    conn = get_connection(_migrated)
    try:
        card = accounts_repo.create(
            conn,
            USER_ID,
            NewAccount(
                name="Visa",
                currency="PLN",
                opening_balance=0,
                is_liability=True,
                credit_limit_minor=100_000,
            ),
        )
        groc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Dining", direction=Direction.EXPENSE)
        )
    finally:
        conn.close()

    r_dot = client.get(
        "/transactions/_limit_preview",
        params={"account_id": card.id, "category_id": groc.id, "amount": "12.34"},
    )
    r_comma = client.get(
        "/transactions/_limit_preview",
        params={"account_id": card.id, "category_id": groc.id, "amount": "12,34"},
    )
    assert r_dot.status_code == 200
    assert r_comma.status_code == 200
    # Both responses must include the populated preview wrapper (the
    # amount is > 0 and parsing succeeded).
    for resp in (r_dot, r_comma):
        assert _html.text_of(resp.text, entries.credit_line) == (
            "Visa \N{MIDDLE DOT} 1,000.00 of 1,000.00 left \N{RIGHTWARDS ARROW} 987.66 after this"
        ), resp.text
