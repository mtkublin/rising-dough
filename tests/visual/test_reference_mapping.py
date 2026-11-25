"""Page-to-route and page-to-modifier mapping of the handoff reference run (T-UR00b, ADR-0147).

Unmarked on purpose: these run in the default suite (the ``visual`` marker is deselected there).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.repositories import accounts as accounts_repo, users as users_repo
from budget_planner.services import (
    accounts as accounts_service,
    invites as invites_service,
    setup as setup_service,
)
from budget_planner.web.app import create_app
from budget_planner.web.auth_cookies import session_cookie_name
from budget_planner.web.middleware.csrf import csrf_cookie_name
from tests.visual import handoff, handoff_seed
from tests.visual.handoff_clicks import CLICK_RECIPES, click_recipe
from tests.visual.handoff_forms import DIALOG_SUBMITS
from tests.visual.handoff_newentry import (
    DIALOG_RECIPES,
    NEWENTRY_RECIPES,
    PHONE_SHEET_DIALOGS,
    dialog_recipe,
    newentry_recipe,
)
from tests.visual.handoff_openers import OPENERS, opener_url
from tests.visual.handoff_recurring import (
    STATE_PAGES,
    STATE_RECIPES,
    STATE_SOURCE,
    state_opener_url,
    state_recipe as dialog_state_recipe,
)
from tests.visual.handoff_states import (
    NO_USER_PAGES,
    RECIPES,
    SETUP_ROUTE,
    SETUP_TOKEN,
    build_empty_db,
    setup_server_env,
    state_recipe,
)
from tests.visual.test_reference import (
    ANONYMOUS_PAGES,
    FORM_SUBMITS,
    LEDGER_BOARD,
    LEDGER_LONG,
    OPENER_PAGES,
    OVERLAY_DIALOGS,
    OVERLAY_MODIFIERS,
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
    mapped = set(OVERLAY_DIALOGS) | OPENER_PAGES | CLICK_PAGES | NEWENTRY_PAGES | STATE_PAGES
    unmapped = {f"pages/overlays/{n}.html" for n in UNMAPPED_OVERLAYS}
    assert mapped | unmapped == overlays
    assert not mapped & unmapped
    assert not set(OVERLAY_DIALOGS) & OPENER_PAGES
    assert not CLICK_PAGES & (set(OVERLAY_DIALOGS) | OPENER_PAGES)
    assert not NEWENTRY_PAGES & (set(OVERLAY_DIALOGS) | OPENER_PAGES | CLICK_PAGES)
    assert not STATE_PAGES & (set(OVERLAY_DIALOGS) | OPENER_PAGES | CLICK_PAGES | NEWENTRY_PAGES)
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
    # The year-cell inline editor is mapped: the recipe clicks the cell (T-UR00b F7).
    assert "override--year-cell" not in UNMAPPED_OVERLAYS
    year_cell = click_recipe("pages/overlays/override--year-cell.html")
    assert year_cell is CLICK_RECIPES["override--year-cell"]


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


def test_typed_dialog_recipes_belong_to_route_opened_new_entry_pages() -> None:
    # The recipe runs after the dialog was fetched from its route, so only OVERLAY_DIALOGS pages
    # (never an input-driven page, which opens its own dialog) may carry one.
    assert set(DIALOG_RECIPES) == set(OVERLAY_DIALOGS)
    assert not set(DIALOG_RECIPES) & NEWENTRY_PAGES
    for page, recipe in DIALOG_RECIPES.items():
        assert dialog_recipe(page) is recipe
    assert dialog_recipe("pages/overlays/new-entry--error.html") is None


# Overlay page -> (route of its own base page, seed modifiers), derived from the handoff file.
_BASES = {
    "edit-account": ("/accounts", ()),
    "edit-account--liability": ("/accounts", ()),
    "reconcile": ("/accounts", ()),
    "new-account": ("/accounts", ()),
    "new-account--filled": ("/accounts", ()),
    "new-account--error": ("/accounts", ()),
    "delete-account": ("/accounts", ("unreferenced-account",)),
    "delete-account--blocked-planned": ("/accounts", ("account-with-rules",)),
    "new-category--filled": ("/settings", ("settings-categories",)),
    "new-category--error": ("/settings", ("settings-categories",)),
    "edit-category": ("/settings", ("settings-categories",)),
    "archive-category": ("/settings", ("settings-categories",)),
    "new-category": ("/settings", ("settings-categories",)),
    "edit-planned": ("/ledger?view=planned", ()),
    "promote--planned": ("/ledger?view=planned", ()),
    "edit-recurring--fixed": ("/ledger?view=recurring", ("recurring-board",)),
    "promote--recurring": ("/ledger?view=recurring", ("recurring-board",)),
    "override--occurrence": ("/ledger?view=recurring", ("recurring-board",)),
    "override--budget-default": ("/plan", ()),
    "override--budget-month": ("/plan", ()),
    "edit-transaction": (LEDGER_BOARD, ()),
    "edit-transaction--transit": (LEDGER_BOARD, ()),
    "new-entry--happened": ("/today?amount=250.00", ()),
    "new-entry--planned": ("/today?amount=250.00", ()),
    "new-entry--repeats-fixed": ("/today?amount=250.00", ()),
    "new-entry--error": ("/today?amount=250.00", ()),
    "new-entry--over-limit": ("/today?amount=250.00", ()),
    "new-entry--phone-sheet": ("/today?amount=250.00", ()),
    "new-entry--repeats-formula": ("/today?amount=250.00", ()),
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
    "new-account--filled": "new account",
    "new-account--error": "new account",
    "delete-account": "Delete Investments E?",
    "delete-account--blocked-planned": "It has no transactions, but 2 recurring rules still use it",
    "new-category--filled": "new category",
    "new-category--error": "new category",
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
    "reset-password": "Reset Ola",  # pragma: allowlist secret - opener id, not a credential
    "one-time-password": "Reset Ola",  # pragma: allowlist secret - opener id, not a credential
    "invite-user": "invite by email",
    "invite-user--error": "invite by email",
    "revoke-invite": "accountant@example.test",
}


def test_every_opener_has_an_expected_dialog_text() -> None:
    assert set(_DIALOG_TEXT) == set(OPENERS)


@pytest.fixture(scope="module")
def seeded(tmp_path_factory: pytest.TempPathFactory) -> tuple[Settings, str]:
    path = tmp_path_factory.mktemp("openers") / "seed.sqlite"
    modifiers = tuple(m for names in OVERLAY_MODIFIERS.values() for m in names)
    token = handoff_seed.build_seed(path, modifiers=modifiers).session_token
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
    # The counts follow the seed: derived through the service that renders the dialog.
    conn = get_connection(settings)
    try:
        (checking,) = (
            a for a in accounts_repo.list_all(conn, handoff_seed.OWNER_ID) if a.name == "Checking"
        )
        refs = accounts_service.account_references(conn, handoff_seed.OWNER_ID, checking.id)
    finally:
        conn.close()
    assert (refs.transactions, refs.planned, refs.recurring) == (33, 2, 8)
    expected = (
        f"{refs.transactions} transactions and {refs.planned + refs.recurring} "
        "planned or recurring items."
    )
    assert expected in text


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
        ("pages/today.html", "/today?amount=250.00", ()),
        ("pages/today--empty.html", "/today?amount=250.00", ("empty",)),
        ("pages/overlays/row-menu--upcoming.html", "/today?amount=250.00", ()),
        ("pages/overlays/shortcuts.html", "/today?amount=250.00", ()),
        ("pages/accounts--empty.html", "/accounts", ("empty-accounts",)),
        ("pages/ledger/actual--empty.html", "/ledger", ("empty-ledger",)),
        ("pages/ledger/actual--long.html", LEDGER_LONG, ("long",)),
        ("pages/ledger/actual.html", LEDGER_BOARD, ()),
        (
            "pages/ledger/actual--no-matches.html",
            LEDGER_BOARD + "&q=pizza",
            ("no-matches",),
        ),
        ("pages/ledger/planned--empty.html", "/ledger?view=planned", ("empty-planned",)),
        ("pages/ledger/recurring--empty.html", "/ledger?view=recurring", ("empty-recurring",)),
        ("pages/settings/categories.html", "/settings", ("settings-categories",)),
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


_STATE_PAGES = {
    "pages/errors/409.html": "/today",
    "pages/errors/500.html": "/today",
    "pages/errors/offline.html": "/today",
    "pages/today--afford-invalid.html": "/today?amount=abc",
    "pages/today--afford-over.html": "/today?amount=1800",
    "pages/today--flash.html": "/today",
    "pages/today--loading.html": "/today",
    "pages/auth/register.html": SETUP_ROUTE,
    "pages/auth/register--error.html": SETUP_ROUTE,
    "pages/auth/force-password.html": "/settings/password",
    "pages/auth/force-password--error.html": "/settings/password",
    "pages/settings/security--error.html": "/settings/security",
}


def test_every_state_page_is_mapped_and_none_is_unmapped() -> None:
    assert UNMAPPED_PAGES == {}
    for page, route in _STATE_PAGES.items():
        assert page in handoff.pages()
        assert route_for(page) == route
    assert f"/setup?token={SETUP_TOKEN}" == SETUP_ROUTE


def test_state_recipes_name_handoff_pages_reached_by_a_request() -> None:
    assert set(RECIPES) == {
        "pages/errors/409.html",
        "pages/errors/500.html",
        "pages/errors/offline.html",
        "pages/today--flash.html",
        "pages/today--loading.html",
        "pages/auth/register--error.html",
        "pages/auth/force-password--error.html",
        "pages/settings/security--error.html",
        "pages/settings/preferences.html",  # F3: the theme click is its request
    }
    # The preferences click recipe belongs to a regular page, not a state page.
    preferences = "pages/settings/preferences.html"
    assert set(RECIPES) - {preferences} <= set(_STATE_PAGES)
    assert preferences not in _STATE_PAGES
    assert route_for(preferences) == "/settings?tab=prefs"
    assert not set(RECIPES) & set(FORM_SUBMITS)
    assert state_recipe("pages/errors/409.html") is RECIPES["pages/errors/409.html"]
    # The afford states and the plain register / force pages are reached by their route alone.
    assert state_recipe("pages/today--afford-over.html") is None
    assert state_recipe("pages/auth/register.html") is None
    assert set(FORM_SUBMITS) == {"pages/auth/login--error.html", "pages/auth/reauth--error.html"}


def test_state_pages_use_their_own_user_and_server_state() -> None:
    assert {"pages/auth/register.html", "pages/auth/register--error.html"} == NO_USER_PAGES
    assert NO_USER_PAGES <= ANONYMOUS_PAGES
    for page in ("pages/auth/force-password.html", "pages/auth/force-password--error.html"):
        assert modifiers_for(page) == ("owner-must-change",)
        assert not is_anonymous(page)
    assert modifiers_for("pages/settings/security--error.html") == ("form-error",)
    assert modifiers_for("pages/today--flash.html") == ()


def _must_change_flags(db: Path) -> list[tuple[int, int]]:
    conn = get_connection(Settings(_env_file=None, database_url=f"sqlite:///{db.as_posix()}"))
    try:
        rows = conn.execute("SELECT id, must_change_password FROM users ORDER BY id").fetchall()
    finally:
        conn.close()
    return [(r["id"], r["must_change_password"]) for r in rows]


def test_owner_must_change_modifier_flags_only_the_owner(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    forced = tmp_path_factory.mktemp("force") / "seed.sqlite"
    handoff_seed.build_seed(forced, modifiers=("owner-must-change",))
    plain = tmp_path_factory.mktemp("plain") / "seed.sqlite"
    handoff_seed.build_seed(plain)
    flags = _must_change_flags(forced)
    base = _must_change_flags(plain)
    assert base[0] == (1, 0)
    assert flags[0] == (1, 1)
    assert flags[1:] == base[1:]  # the seeded users keep theirs (the parent is flagged already)


def test_first_run_setup_is_open_on_the_empty_db_with_the_token_env(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = tmp_path_factory.mktemp("setup") / "empty.sqlite"
    build_empty_db(path)
    env = setup_server_env()
    assert env["BUDGET_ENV"] == "test"
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{path.as_posix()}",
        env="test",
        planner_setup_token_hash=env["BUDGET_PLANNER_SETUP_TOKEN_HASH"],
    )
    conn = get_connection(settings)
    try:
        assert setup_service.is_open(conn, settings)
        assert setup_service.check_token(conn, settings, SETUP_TOKEN)
        assert not setup_service.check_token(conn, settings, "another-token")
    finally:
        conn.close()
    with pytest.raises(FileExistsError):
        build_empty_db(path)


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
        "pages/overlays/new-account.html",
        "pages/overlays/new-account--filled.html",
        "pages/overlays/new-account--error.html",
        "pages/overlays/new-category--filled.html",
        "pages/overlays/new-category--error.html",
        "pages/overlays/override--budget-month.html",
        "pages/overlays/override--budget-every.html",
        "pages/overlays/override--budget-default.html",
    }
    assert not {p for p in DIALOG_SUBMITS if p.split("/")[-1][:-5] in UNMAPPED_OVERLAYS}
    for page, recipe in DIALOG_SUBMITS.items():
        assert page in {f"pages/overlays/{n}.html" for n in OPENERS}
        text = (handoff.HANDOFF_ROOT / page).read_text(encoding="utf-8")
        for _, value in recipe.fills:
            assert f'value="{value}"' in text


def test_used_email_posts_answer_422_with_the_typed_values(seeded: tuple[Settings, str]) -> None:
    settings, token = seeded
    for stem, path, error in (
        ("add-user--error", "/settings/users", "A user with this email already exists"),
        # The invite error reads like the handoff: "This person already has an account" (F3).
        ("invite-user--error", "/settings/users/invites", "This person already has an account"),
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


_STATES = {
    "edit-recurring--empty": "Taxes",
    "edit-recurring--incomplete": "Taxes",
    "edit-recurring--picking": "Taxes",
    "edit-transaction--error": "Takeaway",
    "override--remove": "Big Purchases",
}


def test_state_overlays_are_mapped_with_their_base_pages() -> None:
    assert {p.split("/")[-1][:-5] for p in STATE_PAGES} == set(_STATES) == set(STATE_SOURCE)
    assert not {n for n in STATE_SOURCE if f"pages/overlays/{n}.html" in OPENER_PAGES}
    # edit-account--liability is a recipe on the routed edit dialog (no source of its own)
    assert set(STATE_RECIPES) == (set(STATE_SOURCE) - {"override--remove"}) | {
        "edit-account--liability"
    }
    for stem in ("edit-recurring--empty", "edit-recurring--incomplete", "edit-recurring--picking"):
        page = f"pages/overlays/{stem}.html"
        assert route_for(page) == "/ledger?view=recurring"
        assert modifiers_for(page) == ("recurring-board",)
        assert dialog_state_recipe(page) is STATE_RECIPES[stem]
    assert route_for("pages/overlays/edit-transaction--error.html") == LEDGER_BOARD
    assert route_for("pages/overlays/override--remove.html") == "/ledger?view=recurring"
    assert dialog_state_recipe("pages/overlays/override--remove.html") is None
    assert dialog_state_recipe("pages/today.html") is None


def test_state_openers_resolve_the_dialog_each_state_starts_from(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = tmp_path_factory.mktemp("states") / "seed.sqlite"
    token = handoff_seed.build_seed(path, modifiers=("recurring-board",)).session_token
    settings = Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}", env="test")
    conn = get_connection(settings)
    try:
        urls = {s: state_opener_url(f"pages/overlays/{s}.html", conn) for s in _STATES}
        assert state_opener_url("pages/today.html", conn) is None
        taxes = opener_url("pages/overlays/edit-recurring--formula.html", conn)
        takeaway = opener_url("pages/overlays/edit-transaction.html", conn)
        month = opener_url("pages/overlays/override--budget-month.html", conn)
    finally:
        conn.close()
    assert urls["edit-recurring--empty"] == urls["edit-recurring--picking"] == taxes
    assert urls["edit-recurring--incomplete"] == taxes
    assert urls["edit-transaction--error"] == takeaway
    assert urls["override--remove"] == f"{month}&remove=1"
    for stem, text in _STATES.items():
        url = urls[stem]
        assert url is not None
        status, body, retarget = _get(settings, token, url)
        assert status == 200, stem
        assert text in body, stem
        assert retarget == "#modal-root"


def test_remove_override_confirm_names_the_default_it_falls_back_to(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    path = tmp_path_factory.mktemp("remove") / "seed.sqlite"
    token = handoff_seed.build_seed(path).session_token
    settings = Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}", env="test")
    conn = get_connection(settings)
    try:
        url = state_opener_url("pages/overlays/override--remove.html", conn)
    finally:
        conn.close()
    assert url is not None
    _, body, _ = _get(settings, token, url)
    text = " ".join(re.sub(r"<[^>]+>", " ", body).split())
    assert "Remove override?" in text
    assert "Big Purchases \u00b7 Oct 2026 goes back to the default 604.35 PLN." in text


def test_overlay_modifiers_name_overlays_and_known_modifiers() -> None:
    overlays = {p for p in handoff.pages() if handoff.surface_of(p) == "overlays"}
    assert set(OVERLAY_MODIFIERS) <= overlays
    assert all(set(m) <= set(handoff_seed.MODIFIER_NAMES) for m in OVERLAY_MODIFIERS.values())
