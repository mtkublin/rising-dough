"""E2E: a failing HTMX save shows a visible flash, target kept (T-Q236, ADR-0143)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.ui_map import shell
from tests.ui_map.locator import by_id, to_playwright

pytestmark = pytest.mark.e2e

_PROBE_TARGET = by_id("probe-target")  # injected by _PROBE below

_FLASH_BODY = (
    '<div  id="flash-region-assertive" role="alert" aria-live="assertive" hx-swap-oob="true">'
    '<div class="flash flash-error" data-flash-kind="error"><span>{msg}</span></div></div>'
)
_PROBE = (
    "() => { const t = document.createElement('div'); t.id = 'probe-target';"
    " t.textContent = 'KEEP';"
    " document.getElementById('main').appendChild(t);"
    " htmx.ajax('POST', '/__probe', {target: '#probe-target', swap: 'innerHTML'}); }"
)


def _open(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/ledger")  # old shell page; Today is on the new shell
    assert page.evaluate("typeof window.htmx") == "object"


@pytest.mark.parametrize("status", [404, 409, 500, 503])
def test_server_flash_partial_is_shown_and_target_kept(
    live_server: tuple[str, Path], page: Page, status: int
) -> None:
    base_url, _ = live_server
    _open(page, base_url)
    page.route(
        "**/__probe",
        lambda route: route.fulfill(
            status=status, content_type="text/html", body=_FLASH_BODY.format(msg=f"boom {status}")
        ),
    )
    page.evaluate(_PROBE)
    expect(to_playwright(page, shell.flash_region_assertive)).to_contain_text(f"boom {status}")
    expect(to_playwright(page, _PROBE_TARGET)).to_have_text("KEEP")


@pytest.mark.parametrize("status", [403, 404, 409, 500])
def test_plain_error_body_shows_generic_flash(
    live_server: tuple[str, Path], page: Page, status: int
) -> None:
    base_url, _ = live_server
    _open(page, base_url)
    page.route(
        "**/__probe",
        lambda route: route.fulfill(status=status, content_type="text/plain", body="nope"),
    )
    page.evaluate(_PROBE)
    expect(to_playwright(page, shell.flash_region_assertive)).to_contain_text(re.compile(r"\S"))
    expect(to_playwright(page, _PROBE_TARGET)).to_have_text("KEEP")


def test_form_rerender_on_422_still_swaps(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _open(page, base_url)
    page.route(
        "**/__probe",
        lambda route: route.fulfill(
            status=422, content_type="text/html", body="<p role='alert'>bad value</p>"
        ),
    )
    page.evaluate(_PROBE)
    expect(to_playwright(page, _PROBE_TARGET)).to_have_text("bad value")


def test_network_failure_shows_offline_banner_alone(
    live_server: tuple[str, Path], page: Page
) -> None:
    """Outside a form the offline banner shows alone; no assertive flash (Q29, T-UR02e)."""
    base_url, _ = live_server
    _open(page, base_url)
    page.route("**/__probe", lambda route: route.abort())
    page.evaluate(_PROBE)
    expect(to_playwright(page, shell.flash_region)).to_contain_text("You\u2019re offline")
    page.wait_for_timeout(200)
    expect(to_playwright(page, shell.flash_region_assertive)).not_to_contain_text(
        "Could not reach the server"
    )
