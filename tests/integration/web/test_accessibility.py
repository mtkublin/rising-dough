"""T-052: template-level accessibility assertions.

Runs against rendered HTML for each primary route — no browser needed. Checks:

- Semantic landmarks (`<main id="main">`, header `<nav>`, `<footer>`).
- Skip link is the first interactive element and targets `#main`.
- Flash live regions reserved with correct `role` + `aria-live`.
- Every `<input>` / `<select>` / `<textarea>` is associated with a `<label>`
  (either wrapped or via `for`/`id`) or carries an `aria-label` / `aria-labelledby`.
- Every `<table>` carries a caption; every `<th>` has `scope="col"`.
- `<main>` is programmatically focusable (`tabindex="-1"`) so the skip link lands focus.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

# T-070: /categories now redirects to the Settings drawer, which is a
# fragment (not a full page), so it no longer carries the usual landmarks.
# Every other legacy page URL still redirects to a landmarked full page
# (``/transactions`` → ``/ledger``, ``/budget/manage`` → ``/budget#…``,
# ``/analytics`` → ``/budget#…``). Those are kept here under
# ``follow_redirects=True`` so the full-page assertions keep running.
_ROUTES = (
    "/",
    "/transactions",
    "/accounts",
    "/planned",
    "/recurring",
    "/budget",
    "/budget/manage",
    "/forecast",
    "/analytics",
    # T-071 — new ADR-0023 surfaces.
    "/ledger",
    "/ledger?view=planned",
    "/ledger?view=recurring",
    # Rising Dough v2 surfaces (ADR-0051 §1).
    "/today",
    "/plan",
)


def _soup(client: TestClient, path: str) -> BeautifulSoup:
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"
    return BeautifulSoup(r.text, "html.parser")


@pytest.mark.parametrize("path", _ROUTES)
def test_semantic_landmarks(client: TestClient, path: str) -> None:
    soup = _soup(client, path)
    assert soup.find("main", id="main") is not None
    assert soup.find("header") is not None
    assert soup.find("nav") is not None
    # Single <h1> per page.
    h1s = soup.find_all("h1")
    assert len(h1s) >= 1, f"{path}: no <h1>"


def test_skip_link_is_first_focusable(client: TestClient) -> None:
    soup = _soup(client, "/today")
    skip = soup.find("a", href="#main")
    assert skip is not None
    main = soup.find("main", id="main")
    assert main is not None
    # Make sure <main> is programmatically focusable.
    assert isinstance(main, Tag)
    assert main.get("tabindex") == "-1"


@pytest.mark.parametrize("path", _ROUTES)
def test_flash_live_regions_present(client: TestClient, path: str) -> None:
    soup = _soup(client, path)
    polite = soup.find(id="flash-region")
    assertive = soup.find(id="flash-region-assertive")
    assert polite is not None and isinstance(polite, Tag)
    assert assertive is not None and isinstance(assertive, Tag)
    assert polite.get("role") == "status"
    assert polite.get("aria-live") == "polite"
    assert assertive.get("role") == "alert"
    assert assertive.get("aria-live") == "assertive"


def _control_is_labelled(control: Tag) -> bool:
    """Return True if `control` has a usable accessible name."""
    if control.get("aria-label") or control.get("aria-labelledby"):
        return True
    if control.get("type") in {"hidden", "submit", "button", "reset"}:
        return True
    # Wrapped in a <label>?
    for parent in control.parents:
        if isinstance(parent, Tag) and parent.name == "label":
            return True
    # Explicit `for=id` reference?
    control_id = control.get("id")
    return bool(control_id and control.find_previous("label", attrs={"for": control_id}))


@pytest.mark.parametrize(
    "path",
    (
        # T-070: /categories now redirects to the Settings drawer (fragment),
        # so it is intentionally omitted here; the labelling is still
        # exercised via /settings?tab=categories in test_settings.py.
        "/transactions",
        "/transactions/new",
        "/accounts",
        "/planned",
        "/recurring",
        "/budget/manage",
        "/forecast",
    ),
)
def test_all_form_controls_are_labelled(client: TestClient, path: str) -> None:
    """Every `<input>` / `<select>` / `<textarea>` must have an accessible name."""
    soup = _soup(client, path)
    controls = soup.find_all(["input", "select", "textarea"])
    missing: list[str] = []
    for ctl in controls:
        assert isinstance(ctl, Tag)
        if not _control_is_labelled(ctl):
            missing.append(f"<{ctl.name} name={ctl.get('name')!r}>")
    assert not missing, f"{path}: unlabelled controls → {missing}"


@pytest.mark.parametrize("path", _ROUTES)
def test_tables_have_captions_and_scoped_headers(client: TestClient, path: str) -> None:
    soup = _soup(client, path)
    for table in soup.find_all("table"):
        assert isinstance(table, Tag)
        assert table.find("caption") is not None, f"{path}: table missing <caption>"
        for th in table.find_all("th"):
            assert isinstance(th, Tag)
            assert th.get("scope") in {"col", "row", "colgroup", "rowgroup"}, (
                f"{path}: <th> missing scope attribute"
            )


def test_nav_marks_current_page(client: TestClient) -> None:
    """After T-064 the Ledger rail item owns the legacy /transactions path
    via ``extra_paths``, so visiting /transactions should still highlight it.
    """
    soup = _soup(client, "/transactions")
    nav = soup.find("nav")
    assert nav is not None and isinstance(nav, Tag)
    current = nav.find("a", attrs={"aria-current": "page"})
    assert current is not None and isinstance(current, Tag)
    assert current.get("href") == "/ledger"


def test_dialogs_have_accessible_labels(client: TestClient) -> None:
    """Modal partials from accounts + planned should expose `aria-labelledby`.

    Fetching the fragments directly guarantees the dialog markup renders.
    """
    r = client.get("/accounts")
    assert r.status_code == 200
    # Create an account so we can open the reconcile modal.
    r = client.post(
        "/accounts",
        data={
            "name": "A11y Checking",
            "type": "checking",
            "currency": "PLN",
            "opening_balance": "100",
        },
    )
    assert r.status_code == 200
    # Find the account id via GET /accounts.
    soup = BeautifulSoup(client.get("/accounts").text, "html.parser")

    def _is_account_row(value: str | None) -> bool:
        if not value or not value.startswith("account-"):
            return False
        parts = value.split("-")
        return len(parts) >= 2 and parts[1].isdigit()

    # Rising Dough v2 renders accounts as <tr>, not <article>.
    row = soup.find(["tr", "article"], attrs={"id": _is_account_row})
    assert row is not None and isinstance(row, Tag)
    acc_id = row.get("id").split("-")[1]  # type: ignore[union-attr]
    r = client.get(f"/accounts/{acc_id}/reconcile")
    assert r.status_code == 200
    frag = BeautifulSoup(r.text, "html.parser")
    dialog = frag.find(role="dialog")
    assert dialog is not None and isinstance(dialog, Tag)
    assert dialog.get("aria-labelledby"), "reconcile dialog missing aria-labelledby"
    assert dialog.get("aria-modal") == "true"


def test_settings_drawer_is_dialog(client: TestClient) -> None:
    """Rising Dough v2: Settings page is a full page. HX request still gets
    the drawer fragment with full dialog aria shape."""
    r = client.get("/settings", headers={"HX-Request": "true"})
    assert r.status_code == 200
    frag = BeautifulSoup(r.text, "html.parser")
    drawer = frag.select_one("[data-drawer]")
    assert drawer is not None and isinstance(drawer, Tag)
    assert drawer.get("role") == "dialog"
    assert drawer.get("aria-modal") == "true"
    assert drawer.get("aria-labelledby"), "drawer missing aria-labelledby"
    assert drawer.get("tabindex") == "-1"


def test_slideover_is_dialog(client: TestClient) -> None:
    """T-071: FAB-launched slide-over form carries dialog aria + data-slideover."""
    r = client.get("/transactions/new")
    assert r.status_code == 200
    frag = BeautifulSoup(r.text, "html.parser")
    overlay = frag.select_one("[data-slideover]")
    assert overlay is not None and isinstance(overlay, Tag)
    assert overlay.get("role") == "dialog"
    assert overlay.get("aria-modal") == "true"
    assert overlay.get("aria-labelledby"), "slide-over missing aria-labelledby"


def test_ledger_segmented_marks_active_view(client: TestClient) -> None:
    """Rising Dough v2 — anchor-based rd-segmented; active tab carries aria-selected='true'."""
    soup = _soup(client, "/ledger?view=planned")
    seg = soup.select_one(".rd-segmented")
    assert seg is not None and isinstance(seg, Tag)
    items = seg.select("a.rd-segmented__item")
    assert len(items) >= 3, "expected actual / planned / recurring tabs"
    active = [a for a in items if a.get("aria-selected") == "true"]
    assert len(active) == 1, "exactly one segmented tab should be aria-selected"
    href = active[0].get("href", "")
    assert isinstance(href, str) and href.endswith("view=planned")
