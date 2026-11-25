"""Page-to-route and page-to-modifier mapping of the handoff reference run (T-UR00b, ADR-0147).

Unmarked on purpose: these run in the default suite (the ``visual`` marker is deselected there).
"""

from __future__ import annotations

import datetime as dt
import re

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.repositories import users as users_repo
from budget_planner.services import invites as invites_service
from budget_planner.web.app import create_app
from budget_planner.web.auth_cookies import session_cookie_name
from budget_planner.web.middleware.csrf import csrf_cookie_name
from tests.visual import handoff, handoff_seed
from tests.visual.handoff_clicks import CLICK_RECIPES, click_recipe
from tests.visual.handoff_forms import DIALOG_SUBMITS
from tests.visual.handoff_newentry import (
    NEWENTRY_RECIPES,
    PHONE_SHEET_DIALOGS,
    newentry_recipe,
)
from tests.visual.handoff_openers import OPENERS, opener_url
from tests.visual.test_reference import (
    ANONYMOUS_PAGES,
    FORM_SUBMITS,
    LEDGER_BOARD,
    OPENER_PAGES,
    OVERLAY_DIALOGS,
    PAGE_MODIFIERS,
    PAGE_ROUTES,
    SURFACE_ROUTES,
    UNMAPPED_OVERLAYS,
    UNMAPPED_PAGES,
    base_page_of,
    is_anonymous,
    modifiers_for,
    route_for,
)

CLICK_PAGES = {f"pages/overlays/{n}.html" for n in CLICK_RECIPES}
NEWENTRY_PAGES = set(NEWENTRY_RECIPES)


def test_recurring_reference_uses_board_modifier() -> None:
    assert modifiers_for("pages/ledger/recurring.html") == ("recurring-board",)
    assert route_for("pages/ledger/recurring.html") == "/ledger?view=recurring"
    assert modifiers_for("pages/ledger/planned.html") == ()
    assert all(set(m) <= set(handoff_seed.MODIFIER_NAMES) for m in PAGE_MODIFIERS.values())


def test_every_overlay_page_is_mapped_or_listed_unmapped() -> None:
    overlays = {p for p in handoff.pages() if handoff.surface_of(p) == "overlays"}
    mapped = set(OVERLAY_DIALOGS) | OPENER_PAGES | CLICK_PAGES | NEWENTRY_PAGES
    unmapped = {f"pages/overlays/{n}.html" for n in UNMAPPED_OVERLAYS}
    assert mapped | unmapped == overlays
    assert not mapped & unmapped
    assert not set(OVERLAY_DIALOGS) & OPENER_PAGES
    assert not CLICK_PAGES & (set(OVERLAY_DIALOGS) | OPENER_PAGES)
    assert not NEWENTRY_PAGES & (set(OVERLAY_DIALOGS) | OPENER_PAGES | CLICK_PAGES)
    for page in overlays:
        assert base_page_of(page).startswith("pages/")
        assert handoff.surface_of(base_page_of(page)) != "overlays"
        assert route_for(page) == route_for(base_page_of(page))
    for url in OVERLAY_DIALOGS.values():
        assert url.startswith("/add?when=")


def test_click_recipes_name_handoff_overlays_and_leave_the_unmapped_set() -> None:
    overlays = {p for p in handoff.pages() if handoff.surface_of(p) == "overlays"}
    assert overlays >= CLICK_PAGES
    assert not {n for n in CLICK_RECIPES if n in UNMAPPED_OVERLAYS}
    for name in UNMAPPED_OVERLAYS:
        assert click_recipe(f"pages/overlays/{name}.html") is None
    assert click_recipe("pages/overlays/shortcuts.html") is CLICK_RECIPES["shortcuts"]
    assert click_recipe("pages/today.html") is None
    # The year-cell inline editor does not exist in the app: it stays unmapped.
    assert "override--year-cell" in UNMAPPED_OVERLAYS


def test_new_entry_input_states_are_mapped() -> None:
    names = ("error", "over-limit", "phone-sheet", "repeats-formula")
    assert not {f"new-entry--{n}" for n in names} & UNMAPPED_OVERLAYS
    pages = {f"pages/overlays/new-entry--{n}.html" for n in names}
    assert pages == NEWENTRY_PAGES | set(PHONE_SHEET_DIALOGS)
    # The phone sheet is the happened dialog (identical handoff markup), fetched from its route.
    assert OVERLAY_DIALOGS["pages/overlays/new-entry--phone-sheet.html"] == "/add?when=happened"
    for page in NEWENTRY_PAGES:
        assert newentry_recipe(page) is NEWENTRY_RECIPES[page]
        assert click_recipe(page) is None
    assert newentry_recipe("pages/overlays/new-entry--happened.html") is None


# Overlay page -> (route of its own base page, seed modifiers), derived from the handoff file.
_BASES = {
    "edit-account": ("/accounts", ()),
    "edit-account--liability": ("/accounts", ()),
    "reconcile": ("/accounts", ()),
    "new-account": ("/accounts", ()),
    "edit-category": ("/settings", ()),
    "archive-category": ("/settings", ()),
    "new-category": ("/settings", ()),
    "edit-planned": ("/ledger?view=planned", ()),
    "promote--planned": ("/ledger?view=planned", ()),
    "edit-recurring--fixed": ("/ledger?view=recurring", ("recurring-board",)),
    "promote--recurring": ("/ledger?view=recurring", ("recurring-board",)),
    "override--occurrence": ("/ledger?view=recurring", ("recurring-board",)),
    "override--budget-default": ("/plan", ()),
    "override--budget-month": ("/plan", ()),
    "edit-transaction": (LEDGER_BOARD, ()),
    "edit-transaction--transit": (LEDGER_BOARD, ()),
    "new-entry--happened": ("/today", ()),
    "new-entry--planned": ("/today", ()),
    "new-entry--repeats-fixed": ("/today", ()),
    "new-entry--error": ("/today", ()),
    "new-entry--over-limit": ("/today", ()),
    "new-entry--phone-sheet": ("/today", ()),
    "new-entry--repeats-formula": ("/today", ()),
    "add-user": ("/settings/users", ()),
    "add-user--error": ("/settings/users", ()),
    "edit-user": ("/settings/users", ()),
    "delete-user": ("/settings/users", ()),
    "reset-password": ("/settings/users", ()),
    "one-time-password": ("/settings/users", ()),
    "invite-user": ("/settings/users", ()),
    "invite-user--error": ("/settings/users", ()),
    "revoke-invite": ("/settings/users", ()),
}


@pytest.mark.parametrize("stem", sorted(_BASES))
def test_overlay_renders_over_its_own_base_page(stem: str) -> None:
    page = f"pages/overlays/{stem}.html"
    route, modifiers = _BASES[stem]
    assert route_for(page) == route
    assert modifiers_for(page) == modifiers


# Text each dialog must show once opened from its resolved route (the handoff names).
_DIALOG_TEXT = {
    "new-account": "new account",
    "edit-account": "Investments A",
    "edit-account--liability": "Investments A",
    "delete-account--blocked": "Checking",
    "reconcile": "Checking",
    "reconcile--liability": "Credit Card",
    "new-category": "new category",
    "edit-category": "Takeaway",
    "archive-category": "Takeaway",
    "edit-planned": "Car",
    "promote--planned": "Car",
    "edit-recurring--fixed": "Fixed Costs",
    "edit-recurring--formula": "Taxes",
    "promote--recurring": "Fixed Costs",
    "override--occurrence": "Fixed costs",
    "override--budget-month": "Big Purchases",
    "override--budget-every": "Big Purchases",
    "override--budget-default": "Big Purchases",
    "edit-transaction": "Takeaway",
    "edit-transaction--transit": "Transit",
    "add-user": "add user",
    "add-user--error": "add user",
    "edit-user": "partner@example.test",
    "delete-user": "Delete Ola?",
    "reset-password": "Reset Ola",  # pragma: allowlist secret (overlay stem, not a credential)
    "one-time-password": "Reset Ola",  # pragma: allowlist secret (overlay stem, not a credential)
    "invite-user": "create invite",
    "invite-user--error": "create invite",
    "revoke-invite": "accountant@example.test",
}


def test_every_opener_has_an_expected_dialog_text() -> None:
    assert set(_DIALOG_TEXT) == set(OPENERS)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Settings, str]:
    path = tmp_path_factory.mktemp("openers") / "seed.sqlite"
    token = handoff_seed.build_seed(path).session_token
    settings = Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}", env="test")
    return settings, token


def _url(settings: Settings, stem: str) -> str:
    conn = get_connection(settings)
    try:
        url = opener_url(f"pages/overlays/{stem}.html", conn)
    finally:
        conn.close()
    assert url is not None
    assert "{" not in url
    return url


def _get(settings: Settings, token: str, url: str) -> tuple[int, str, str]:
    with (
        clock.frozen(dt.datetime.fromisoformat(handoff.HANDOFF_FIXED_TIME)),
        TestClient(create_app(settings)) as client,
    ):
        client.cookies.set(session_cookie_name(settings), token)
        response = client.get(url, headers={"HX-Request": "true"})
    return response.status_code, response.text, response.headers.get("HX-Retarget", "")


@pytest.mark.parametrize("stem", sorted(OPENERS))
def test_opener_route_serves_its_dialog(stem: str, seeded: tuple[Settings, str]) -> None:
    settings, token = seeded
    url = _url(settings, stem)
    status, body, retarget = _get(settings, token, url)
    assert status == 200, url
    assert "<dialog" in body
    assert _DIALOG_TEXT[stem] in body
    assert retarget == "#modal-root"


def test_recurring_openers_resolve_in_the_recurring_board_seed(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = tmp_path_factory.mktemp("board") / "seed.sqlite"
    token = handoff_seed.build_seed(path, modifiers=("recurring-board",)).session_token
    settings = Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}", env="test")
    for stem in ("edit-recurring--fixed", "promote--recurring", "override--occurrence"):
        status, body, _ = _get(settings, token, _url(settings, stem))
        assert status == 200, stem
        assert _DIALOG_TEXT[stem] in body


def test_new_entry_overlays_open_the_dialog_from_add(seeded: tuple[Settings, str]) -> None:
    settings, token = seeded
    for url in OVERLAY_DIALOGS.values():
        status, body, retarget = _get(settings, token, url)
        assert status == 200, url
        assert "<dialog" in body
        assert retarget == "#modal-root"


def test_delete_opener_opens_the_blocked_variant(seeded: tuple[Settings, str]) -> None:
    settings, token = seeded
    status, body, _ = _get(settings, token, _url(settings, "delete-account--blocked"))
    assert status == 200
    text = " ".join(re.sub(r"<[^>]+>", " ", body).split())
    assert "Can\u2019t delete Checking It still has" in text
    assert "23 transactions and 3 planned items and 7 recurring rules." in text


def _non_overlay_pages() -> set[str]:
    return {p for p in handoff.pages() if handoff.surface_of(p) != "overlays"}


def test_every_page_is_mapped_or_listed_unmapped() -> None:
    pages = _non_overlay_pages()
    auth = {p for p in pages if handoff.surface_of(p) == "auth"}
    errors = {p for p in pages if handoff.surface_of(p) == "errors"}
    assert auth <= set(PAGE_ROUTES) | set(UNMAPPED_PAGES)
    assert errors <= set(PAGE_ROUTES) | set(UNMAPPED_PAGES) | {"pages/errors/404.html"}
    assert set(UNMAPPED_PAGES) <= pages
    assert not set(UNMAPPED_PAGES) & set(FORM_SUBMITS)
    for page in pages:
        assert handoff.surface_of(page) in SURFACE_ROUTES
    for page in set(PAGE_ROUTES) | set(PAGE_MODIFIERS) | set(FORM_SUBMITS) | ANONYMOUS_PAGES:
        assert page in pages


@pytest.mark.parametrize(
    ("page", "route", "modifiers"),
    [
        ("pages/auth/login.html", "/auth/login", ()),
        ("pages/auth/login--error.html", "/auth/login", ("form-error",)),
        ("pages/auth/invite.html", "/invite/handoff-invite-accountant", ()),
        (
            "pages/auth/invite--expired.html",
            "/invite/handoff-invite-accountant",
            ("invite-expired",),
        ),
        ("pages/auth/invite--used.html", "/invite/handoff-invite-accountant", ("invite-used",)),
        ("pages/auth/invite--invalid.html", "/invite/not-a-real-invite-token", ()),
        ("pages/auth/reauth.html", "/auth/reauth", ()),
        ("pages/auth/reauth--error.html", "/auth/reauth", ("form-error",)),
        ("pages/today--empty.html", "/today", ("empty",)),
        ("pages/accounts--empty.html", "/accounts", ("empty-accounts",)),
        ("pages/ledger/actual--empty.html", "/ledger", ("empty-ledger",)),
        ("pages/ledger/actual--long.html", LEDGER_BOARD, ("long",)),
        ("pages/ledger/actual.html", LEDGER_BOARD, ()),
        (
            "pages/ledger/actual--no-matches.html",
            LEDGER_BOARD + "&q=pizza",
            ("no-matches",),
        ),
        ("pages/ledger/planned--empty.html", "/ledger?view=planned", ("empty-planned",)),
        ("pages/ledger/recurring--empty.html", "/ledger?view=recurring", ("empty-recurring",)),
        ("pages/settings/categories.html", "/settings", ()),
        ("pages/settings/preferences.html", "/settings?tab=prefs", ()),
        ("pages/settings/currency-fx.html", "/settings?tab=fx", ()),
        ("pages/settings/security.html", "/settings/security", ()),
        ("pages/settings/users.html", "/settings/users", ()),
        ("pages/errors/422.html", "/budget?month=zz", ()),
    ],
)
def test_page_route_and_modifiers(page: str, route: str, modifiers: tuple[str, ...]) -> None:
    assert route_for(page) == route
    assert modifiers_for(page) == modifiers
    assert set(modifiers) <= set(handoff_seed.MODIFIER_NAMES)


def test_only_signed_out_auth_pages_are_anonymous() -> None:
    assert all(p.startswith("pages/auth/") for p in ANONYMOUS_PAGES)
    assert is_anonymous("pages/auth/login.html")
    assert is_anonymous("pages/auth/invite--used.html")
    assert not is_anonymous("pages/auth/reauth.html")
    assert not is_anonymous("pages/auth/reauth--error.html")
    assert not is_anonymous("pages/today.html")


def test_unmapped_pages_carry_a_reason() -> None:
    assert set(UNMAPPED_PAGES) == {
        "pages/auth/register.html",
        "pages/auth/register--error.html",
        "pages/auth/force-password.html",
        "pages/auth/force-password--error.html",
        "pages/settings/security--error.html",
        "pages/errors/409.html",
        "pages/errors/500.html",
        "pages/errors/offline.html",
        "pages/today--afford-invalid.html",
        "pages/today--afford-over.html",
        "pages/today--flash.html",
        "pages/today--loading.html",
    }
    assert all(len(reason) > 20 for reason in UNMAPPED_PAGES.values())
    assert set(FORM_SUBMITS) == {"pages/auth/login--error.html", "pages/auth/reauth--error.html"}


def test_user_openers_resolve_ids_by_email_from_the_seed(seeded: tuple[Settings, str]) -> None:
    settings, _ = seeded
    conn = get_connection(settings)
    try:
        ola = next(u.id for u in users_repo.list_live(conn) if u.email == "partner@example.test")
        invite = next(
            i.id for i in invites_service.list_invites(conn) if i.email == "accountant@example.test"
        )
    finally:
        conn.close()
    assert _url(settings, "edit-user") == f"/settings/users/{ola}/edit"
    assert _url(settings, "delete-user") == f"/settings/users/{ola}/delete"
    assert _url(settings, "reset-password") == f"/settings/users/{ola}/reset-password"
    assert _url(settings, "revoke-invite") == f"/settings/users/invites/{invite}/revoke"


def test_post_state_recipes_type_what_the_handoff_shows() -> None:
    assert set(DIALOG_SUBMITS) == {
        "pages/overlays/add-user--error.html",
        "pages/overlays/invite-user--error.html",
        "pages/overlays/one-time-password.html",
    }
    for page, recipe in DIALOG_SUBMITS.items():
        assert page in {f"pages/overlays/{n}.html" for n in OPENERS}
        text = (handoff.HANDOFF_ROOT / page).read_text(encoding="utf-8")
        for _, value in recipe.fills:
            assert f'value="{value}"' in text


def test_used_email_posts_answer_422_with_the_typed_values(seeded: tuple[Settings, str]) -> None:
    settings, token = seeded
    for stem, path, error in (
        ("add-user--error", "/settings/users", "A user with this email already exists"),
        # The app words the invite error like the add-user one; the handoff reads "This person
        # already has an account" (a copy difference reported for the migration, not mapped).
        ("invite-user--error", "/settings/users/invites", "A user with this email already exists"),
    ):
        recipe = DIALOG_SUBMITS[f"pages/overlays/{stem}.html"]
        data = {sel.rsplit("name=", 1)[1].rstrip("]"): value for sel, value in recipe.fills}
        with (
            clock.frozen(dt.datetime.fromisoformat(handoff.HANDOFF_FIXED_TIME)),
            TestClient(create_app(settings), base_url="https://testserver") as client,
        ):
            client.cookies.set(session_cookie_name(settings), token)
            client.get("/settings/users")  # mints the CSRF cookie the form would carry
            csrf = client.cookies.get(csrf_cookie_name(settings)) or ""
            response = client.post(
                path, data=data, headers={"HX-Request": "true", "X-CSRF-Token": csrf}
            )
        assert response.status_code == 422, stem
        text = " ".join(re.sub(r"<[^>]+>", " ", response.text).split())
        assert error in text, stem
        assert 'value="partner@example.test"' in response.text
