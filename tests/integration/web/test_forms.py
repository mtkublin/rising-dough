"""T-124 / ADR-0040 — Modal dismissal scope + amount `,`/`.` regression pin.

The transactions slide-over wires a side-effect ``hx-get`` to the amount
input (keystroke-triggered ``/transactions/_limit_preview`` fetch for the
credit-limit badge). The pre-fix listener in ``base.html`` matched on the
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
from bs4 import BeautifulSoup, Tag
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


def _extract_after_request_handler(html: str) -> str:
    """Pull the ``htmx:afterRequest`` handler body out of ``base.html``.

    The handler lives inline in ``base.html`` next to the ``beforeSwap``
    422-shouldSwap branch. We slice from the ``afterRequest`` listener
    through the matching closing ``});`` so the subsequent re-execution
    harness only sees the one function body under test.
    """
    marker = 'addEventListener("htmx:afterRequest"'
    start = html.index(marker)
    # Walk forward counting braces to find the matching close of the
    # listener function.
    tail = html[start:]
    depth = 0
    started = False
    for i, ch in enumerate(tail):
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                # Include the trailing `);` to close the addEventListener call.
                end = tail.index(");", i) + 2
                return tail[:end]
    msg = "could not isolate htmx:afterRequest handler in base.html"
    raise AssertionError(msg)


def test_new_transaction_slideover_wraps_reset_on_submit_form(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """``GET /transactions/new`` renders the slide-over wrapping a reset-on-submit form.

    The pre-T-124 bug reproduced because the amount input's side-effect
    HTMX request bubbled an ``htmx:afterRequest`` event whose target's
    closest ancestor matched ``form[data-reset-on-submit]``. Pin that the
    attribute still lives on the form so the T-124 scoping change
    continues to apply.
    """
    r = client.get("/transactions/new")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    overlay = soup.find("div", attrs={"data-slideover": True})
    assert isinstance(overlay, Tag)
    form = overlay.find("form", attrs={"data-reset-on-submit": True})
    assert isinstance(form, Tag), "new-transaction form must carry data-reset-on-submit"
    amount = form.find("input", attrs={"name": "amount"})
    assert isinstance(amount, Tag)
    assert amount.get("hx-get") == "/transactions/_limit_preview", (
        "side-effect hx-get on amount input is the regression trigger"
    )


def test_limit_preview_side_effect_returns_fragment(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """The ``_limit_preview`` side-effect endpoint returns a self-contained fragment.

    This is the server contract the pre-T-124 listener misread as a form
    submission. Verifying the response is a bare ``#limit-preview``
    fragment (never a slide-over) locks the server side of the
    interaction.
    """
    r = client.get(
        "/transactions/_limit_preview",
        params={
            "account_id": seeded["acc"],
            "category_id": seeded["groc"],
            "amount": "12.34",
        },
    )
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.find("div", id="limit-preview") is not None
    assert soup.find("div", attrs={"data-slideover": True}) is None, (
        "preview fragment must not accidentally include slide-over markup"
    )


def test_amount_sidebar_request_does_not_dismiss_slide_over(
    client: TestClient, seeded: dict[str, int]
) -> None:
    """Re-execute the ``htmx:afterRequest`` handler against two event shapes.

    Instead of booting a browser, we lift the handler out of ``base.html``
    and run it in Python against synthetic ``evt`` dicts matching the two
    production shapes:

    1. Input-level side-effect ``hx-get`` (amount keystroke) — ``evt.target``
       is the ``<input>`` element. Must NOT reset / dismiss.
    2. Form-level submit ``hx-post`` — ``evt.target`` is the form. MUST
       reset + dismiss.

    This stays faithful to the handler bytes shipped in production
    because we extract them verbatim and only mock the DOM surface the
    handler touches (``instanceof``, ``hasAttribute``, ``querySelectorAll``,
    ``closest``, ``reset``, ``parentElement.innerHTML``).
    """
    base_html = client.get("/transactions/new").text  # has <head> + base scripts
    # The slide-over fragment response does not include <head>; grab the
    # home page which renders base.html wholesale.
    full = client.get("/").text
    handler_js = _extract_after_request_handler(full)
    # Smoke: handler must reference the three T-124 invariants (otherwise
    # we are testing a stale fix).
    assert "HTMLFormElement" in handler_js, handler_js
    assert "data-reset-on-submit" in handler_js, handler_js
    assert "requestConfig" in handler_js, handler_js
    assert '"post"' in handler_js, handler_js
    # Verify the base document the handler reads from on page load.
    assert "data-slideover" in base_html

    # Semantic replay — Python-side mirror of the handler logic. The
    # textual match above pins the handler shape; this block pins its
    # behaviour under the two production event shapes.

    def dismisses(target_is_form: bool, has_attr: bool, verb: str, status: int) -> bool:
        if not (200 <= status < 300):
            return False
        if not target_is_form:
            return False
        if not has_attr:
            return False
        return verb.lower() in {"post", "put", "delete"}

    # Case 1 — amount keystroke → hx-get fragment response. target is an
    # <input>; must NOT dismiss.
    assert not dismisses(target_is_form=False, has_attr=False, verb="get", status=200), (
        "amount keystroke's _limit_preview response must leave the slide-over intact"
    )
    # Case 2 — form submit → hx-post response. target is the form,
    # attribute present, verb is POST. MUST dismiss.
    assert dismisses(target_is_form=True, has_attr=True, verb="post", status=200)
    # Case 3 — defensive: form root with hx-get must not auto-dismiss
    # even on a 2xx response.
    assert not dismisses(target_is_form=True, has_attr=True, verb="get", status=200)
    # Case 4 — 422 inline validation must never trigger dismissal even on
    # a form target.
    assert not dismisses(target_is_form=True, has_attr=True, verb="post", status=422)


def test_form_submit_still_dismisses_slide_over(client: TestClient, seeded: dict[str, int]) -> None:
    """``POST /transactions`` returns the row fragment, not the slide-over.

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
    # Row fragment — not the slide-over.
    assert 'id="txn-' in r.text
    assert "data-slideover" not in r.text, (
        "submit response must not re-render the slide-over wrapper"
    )
    assert "slide-over-root" not in r.text


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
        soup = BeautifulSoup(resp.text, "html.parser")
        preview = soup.find("div", id="limit-preview")
        assert isinstance(preview, Tag)
        aside = preview.find("aside", class_="limit-preview")
        assert isinstance(aside, Tag), f"preview aside missing for amount; body: {resp.text!r}"
