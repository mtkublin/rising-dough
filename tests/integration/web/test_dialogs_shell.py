"""Shared dialog shell and row-menu item kinds on /dev/shell (T-UR04e, ADR-0107 section 2).

Every variant goes through ``dialogs.dialog_response``: the template lands in
``#modal-root`` inside one bare wrapper, ids and aria wiring match the handoff
overlays (``aria-labelledby`` -> ``<id>-title``).
"""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from tests.ui_map import _html, rd_dialogs as d, rd_fragments as f
from tests.ui_map.locator import by_id, label, role

HX = {"HX-Request": "true"}


def _open(client: TestClient, variant: str) -> tuple[str, str]:
    r = client.get(f"/dev/shell/dialog/{variant}", headers=HX)
    assert r.headers["hx-retarget"] == "#modal-root"
    assert r.headers["hx-reswap"] == "innerHTML"
    return str(r.status_code), r.text


def test_standard_dialog_has_band_hero_body_and_actions(client: TestClient) -> None:
    status, html = _open(client, "standard")
    assert status == "200"
    dlg = d.dev_standard
    el = _html.resolve_one(html, dlg)
    assert (el.get("id"), el.get("aria-labelledby"), el.get("data-js")) == (
        "dev-standard",
        "dev-standard-title",
        "modal",
    )
    assert _html.text_of(html, role("heading", "new account")) == "new account"
    assert _html.exists(html, d.close_button(dlg))
    amount = _html.resolve_one(html, d.hero_amount(dlg, "Opening balance"))
    assert (amount.get("name"), amount.get("value"), amount.get("data-js")) == (
        "amount",
        "0.00",
        "amount-input",
    )
    assert _html.text_of(html, by_id("hero-amount")) == ""
    assert "opening balance" in _html.all_text(html, dlg)
    names = [_html.accessible_name(b) for b in _html.resolve(html, role("button").inside(dlg))]
    assert names == [
        "Close",
        "cancel",
        "[ create account ]",
    ]
    form = _html.resolve_one(html, d.dev_standard).find("form")
    assert form is not None
    assert (form.get("method"), form.get("hx-post"), form.get("hx-target")) == (
        "post",
        "/dev/shell/dialog/standard",
        "#modal-root",
    )
    assert not _html.exists(html, d.error_summary(dlg))


def test_confirm_dialog_is_an_alertdialog_with_a_destructive_submit(client: TestClient) -> None:
    _, html = _open(client, "confirm")
    el = _html.resolve_one(html, d.dev_confirm)
    assert (el.get("role"), el.get("aria-labelledby"), el.get("id")) == (
        "alertdialog",
        "dev-confirm-title",
        "dev-confirm",
    )
    assert el.get("class") == ["rd-dialog", "rd-dialog--sm", "rd-dialog--confirm"]
    assert not _html.exists(html, d.close_button(d.dev_confirm))
    delete = _html.resolve_one(html, d.action(d.dev_confirm, "delete account"))
    assert (delete.get("type"), delete.get("name"), delete.get("value")) == (
        "submit",
        "delete",
        "1",
    )
    assert delete.get("class") == ["rd-btn", "rd-btn--lg", "rd-btn--danger"]
    assert _html.exists(html, d.action(d.dev_confirm, "cancel"))


def test_blocked_dialog_has_no_form_and_no_primary_submit(client: TestClient) -> None:
    _, html = _open(client, "blocked")
    el = _html.resolve_one(html, d.dev_blocked)
    assert el.get("aria-labelledby") == "dev-blocked-title"
    assert el.find("form") is None
    link = _html.resolve_one(html, d.action_link(d.dev_blocked, "view 84 transactions"))
    assert link.get("href") == "/dev/shell"
    ok = _html.resolve_one(html, d.action(d.dev_blocked, "[ ok ]"))
    assert (ok.get("type"), ok.get("data-js")) == ("button", "dialog-close")
    assert "It still has 84 transactions" in _html.all_text(html, d.dev_blocked)


def test_phone_sheet_variant_is_the_standard_markup_with_a_signed_hero(
    client: TestClient,
) -> None:
    _, html = _open(client, "sheet")
    el = _html.resolve_one(html, d.dev_sheet)
    assert el.get("aria-labelledby") == "dev-sheet-title"
    amount = _html.resolve_one(html, d.hero_amount(d.dev_sheet))
    assert amount.get("value") == "35.50"
    text = " ".join(_html.all_text(html, d.dev_sheet).split())
    assert "\u2212" in text
    assert "PLN" in text


def test_invalid_dialog_is_422_with_summary_and_two_field_errors(client: TestClient) -> None:
    status, html = _open(client, "invalid")
    assert status == "422"
    dlg = _html.resolve_one(html, d.dialog("new account"))
    assert dlg.get("id") == "dev-invalid"
    summary = _html.resolve_one(html, d.error_summary(d.dialog("new account")))
    assert summary.get("id") == "error-summary"
    assert " ".join(summary.get_text().split()) == (
        "2 fields need attention Amount: Enter an amount above 0.00 Name: Name is required"
    )
    assert [a.get("href") for a in summary.find_all("a")] == ["#field-amount", "#field-name"]
    amount = _html.resolve_one(html, label("Opening balance", exact=True))
    assert (amount.get("id"), amount.get("aria-invalid"), amount.get("aria-describedby")) == (
        "field-amount",
        "true",
        "field-amount-error",
    )
    assert _html.text_of(html, by_id("field-amount-error")) == "▲ Enter an amount above 0.00"
    assert _html.text_of(html, by_id("field-name-error")) == "▲ Name is required"


def test_form_variants_post_back_422_and_confirm_posts_back_a_flash(client: TestClient) -> None:
    bad = client.post("/dev/shell/dialog/standard", headers=HX)
    assert bad.status_code == 422
    assert bad.headers["hx-retarget"] == "#modal-root"
    assert _html.exists(bad.text, d.error_summary(d.dialog("new account")))
    ok = client.post("/dev/shell/dialog/confirm", headers=HX)
    assert ok.status_code == 200
    assert "Dev account deleted" in _html.page_text(ok.text)
    modal_root = _html.resolve_one(ok.text, by_id("modal-root"))
    assert (modal_root.get("hx-swap-oob"), modal_root.get_text()) == ("innerHTML", "")


def test_unknown_variant_is_rejected(client: TestClient) -> None:
    assert client.get("/dev/shell/dialog/nope", headers=HX).status_code == 422


def test_dev_row_menu_renders_every_item_kind(client: TestClient) -> None:
    html = client.get("/dev/shell").text
    items = {
        i.get_text(strip=True): i for i in _html.resolve(html, role("menuitem").inside(f.row_menu))
    }
    assert list(items) == [
        "standard",
        "invalid",
        "sheet",
        "blocked",
        "delete",
        "plain link",
        "post toast",
        "cancel",
    ]
    std = items["standard"]
    assert (std.name, std.get("href"), std.get("hx-get"), std.get("hx-target")) == (
        "a",
        "/dev/shell/dialog/standard",
        "/dev/shell/dialog/standard",
        "#modal-root",
    )
    assert std.get("hx-swap") == "innerHTML"
    assert items["sheet"].get("class") == ["rd-menu__item", "rd-menu__item--phone"]
    assert items["delete"].get("class") == ["rd-menu__item", "rd-menu__item--danger"]
    plain = items["plain link"]
    assert (plain.get("href"), plain.get("hx-get")) == ("/dev/shell", None)
    post = items["post toast"]
    assert (post.name, post.get("hx-post"), post.get("hx-swap"), post.get("hx-confirm")) == (
        "button",
        "/dev/shell/toast",
        "none",
        "Show the dev toast?",
    )
    cancel = items["cancel"]
    assert (cancel.get("popovertarget"), cancel.get("popovertargetaction")) == (
        "dev-row-menu",
        "hide",
    )


# ---------------------------------------------------------------------------
# Markup parity with the handoff overlays (ADR-0107 section 2)
# ---------------------------------------------------------------------------

_OVERLAYS = Path(__file__).resolve().parents[3] / "docs/design/rising-dough-frontend/pages/overlays"


def _skeleton(html: str) -> dict[str, object]:
    """Classes, roles and aria wiring of the dialog, its chrome and its actions, ids normalised."""
    dlg = BeautifulSoup(html, "html.parser").find("dialog")
    assert isinstance(dlg, Tag)
    dlg_id = str(dlg.get("id"))
    footer = dlg.find(class_="rd-dialog__actions")
    assert isinstance(footer, Tag)

    def norm(value: object) -> object:
        return str(value).replace(dlg_id, "ID") if isinstance(value, str) else value

    def chrome(*classes: str) -> object:
        return [
            (e.name, e.get("class"), norm(e.get("id")), e.get("role"))
            for e in dlg.find_all(class_=lambda c: c in classes)
        ]

    return {
        "dialog": (
            dlg.get("class"),
            dlg.get("role"),
            dlg.get("data-js"),
            norm(dlg.get("aria-labelledby")),
        ),
        "form": [(f.get("class"), f.get("method")) for f in dlg.find_all("form")],
        "band": chrome(
            ".rd-dialog__band, .rd-dialog__band-head, .rd-dialog__hero, .rd-dialog__hero-row"
        ),
        "title": chrome("rd-dialog__title", "rd-dialog__confirm", "rd-dialog__confirm-title"),
        "close": [
            (c.get("class"), c.get("aria-label"), c.get("data-js"), c.get("type"))
            for c in dlg.find_all("button", class_="rd-dialog__close")
        ],
        "body": chrome("rd-dialog__body", "rd-dialog__actions"),
        "actions": [
            (
                a.name,
                a.get("class"),
                a.get("type"),
                a.get("name"),
                a.get("value"),
                a.get("data-js"),
                " ".join(a.get_text().split()),
            )
            for a in footer.find_all(recursive=False)
        ],
    }


def _handoff(name: str) -> dict[str, object]:
    skeleton = _skeleton((_OVERLAYS / f"{name}.html").read_text())
    assert skeleton["actions"] and skeleton["title"], f"{name}: nothing parsed from the handoff"
    return skeleton


def test_standard_matches_the_new_account_overlay(client: TestClient) -> None:
    _, html = _open(client, "standard")
    assert _skeleton(html) == _handoff("new-account")


def test_confirm_matches_the_delete_account_overlay(client: TestClient) -> None:
    _, html = _open(client, "confirm")
    assert _skeleton(html) == _handoff("delete-account")


def test_blocked_matches_the_delete_account_blocked_overlay(client: TestClient) -> None:
    _, html = _open(client, "blocked")
    assert _skeleton(html) == _handoff("delete-account--blocked")


# ---------------------------------------------------------------------------
# Action API: named primary, secondary hx_get, ids
# ---------------------------------------------------------------------------


def test_reconcile_like_variant_has_named_primary_and_a_secondary_button(
    client: TestClient,
) -> None:
    _, html = _open(client, "reconcile")
    dlg = d.dialog("reconcile Checking")
    primary = _html.resolve_one(html, d.action(dlg, "[ reconcile ]"))
    assert (primary.get("id"), primary.get("type"), primary.get("name"), primary.get("value")) == (
        "dev-reconcile-apply",
        "submit",
        "apply",
        "1",
    )
    assert primary.get("class") == ["rd-btn", "rd-btn--lg", "rd-btn--primary"]
    sec = _html.resolve_one(html, d.action(dlg, "preview"))
    assert dict(sec.attrs) == {
        "id": "dev-reconcile-preview",
        "type": "button",
        "class": ["rd-btn", "rd-btn--lg"],
        "hx-get": "/dev/shell/dialog/standard",
        "hx-target": "#modal-root",
        "hx-swap": "innerHTML",
    }
