"""Page-level crawling: discover controls, activate them, collect problems."""

from __future__ import annotations

import contextlib
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from playwright.sync_api import ElementHandle, Error as PlaywrightError, Page

from tests.e2e.crawl.dom import (
    CONTROL_ELEMENTS_JS,
    DIAGNOSTICS_JS,
    FIND_CONTROLS_JS,
    HTMX_COUNTER_JS,
    SIGNATURE_JS,
    Control,
)

SETTLE_MS = 150
BUSY_TIMEOUT_MS = 4000
CLICK_TIMEOUT_MS = 3000
DESKTOP = {"width": 1440, "height": 900}
TABLET = {"width": 1024, "height": 768}
MOBILE = {"width": 375, "height": 800}

# Controls the crawler must not drive, with the reason (recorded in the
# inventory as ``skipped``). Matched on (kind, normalised target prefix).
SKIP_TARGETS: tuple[tuple[str, str], ...] = (
    ("/auth/logout", "ends the crawler's own session"),
    ("/auth/passkeys/", "needs a WebAuthn authenticator"),
    ("/auth/register", "needs a WebAuthn authenticator"),
)


SKIP_NAMES: tuple[tuple[str, str], ...] = (("Add passkey", "needs a WebAuthn authenticator"),)


def skip_reason(control: Control) -> str | None:  # noqa: PLR0911
    if control.external:
        return "external link"
    if control.offscreen:
        return "off-screen or visually hidden (skip link, sr-only)"
    if control.nonclick:
        return "triggered by input or form event, not a click"
    if control.disabled:
        return "disabled"
    for name, why in SKIP_NAMES:
        if control.name == name:
            return why
    for prefix, why in SKIP_TARGETS:
        if control.target.startswith(prefix):
            return why
    return None


class Recorder:
    """Collects console errors, 4xx/5xx responses and failed requests."""

    def __init__(self, page: Page, base_url: str) -> None:
        self._base = base_url
        self.problems: list[str] = []
        page.on("console", self._on_console)
        page.on("pageerror", lambda e: self.problems.append(f"pageerror: {e}"))
        page.on("response", self._on_response)
        page.add_init_script(HTMX_COUNTER_JS)
        page.on("dialog", lambda d: d.accept())  # hx-confirm prompts
        page.on("requestfailed", self._on_failed)

    def _on_console(self, msg: Any) -> None:
        message = str(msg.text)
        if msg.type == "error" and not re.search(r"status of (422|409)|Error Code 409", message):
            self.problems.append(f"console.error: {message}")

    def _on_response(self, resp: Any) -> None:
        if resp.status in (409, 422) and resp.request.method == "POST":
            # 422: server-side form validation; 409: a domain refusal (delete of an account
            # with a balance or references, F2.2a / F2.8). htmx swaps the message in.
            return
        if resp.url.startswith(self._base) and resp.status >= 400:
            self.problems.append(f"HTTP {resp.status}: {resp.request.method} {resp.url}")

    def _on_failed(self, req: Any) -> None:
        reason = req.failure or ""
        if "ERR_ABORTED" in str(reason):  # navigation cancelled an in-flight request
            return
        self.problems.append(f"requestfailed: {req.method} {req.url} {reason}")

    def drain(self) -> list[str]:
        out, self.problems = self.problems, []
        return out


def settle(page: Page) -> None:
    """Wait for htmx to finish swapping, then a short grace period."""
    page.wait_for_timeout(SETTLE_MS)  # let a click-initiated navigation commit
    page.wait_for_load_state("load")
    with contextlib.suppress(PlaywrightError):  # a stuck request is reported by the effect check
        page.wait_for_function(
            "() => !document.querySelector('.htmx-request, .htmx-swapping, .htmx-settling')",
            timeout=BUSY_TIMEOUT_MS,
        )
    page.wait_for_timeout(SETTLE_MS)


def find_controls(page: Page) -> list[Control]:
    return [Control.from_js(raw) for raw in page.evaluate(FIND_CONTROLS_JS)]


def stable_controls(page: Page) -> list[Control]:
    """Controls once opening animations finished (same set on two consecutive reads)."""
    current = find_controls(page)
    for _ in range(6):
        page.wait_for_timeout(SETTLE_MS)
        latest = find_controls(page)
        if [c.key for c in latest] == [c.key for c in current]:
            return latest
        current = latest
    return current


def element_for(page: Page, control: Control) -> ElementHandle | None:
    metas = find_controls(page)
    handles = page.evaluate_handle(CONTROL_ELEMENTS_JS)
    for index, meta in enumerate(metas):
        if meta.key == control.key:
            return handles.get_property(str(index)).as_element()
    return None


def diagnose(page: Page, label: str) -> list[str]:
    """Overflow and duplicate-id checks (frontend-visual-audit signals)."""
    diag = page.evaluate(DIAGNOSTICS_JS)
    problems = [f"{label}: duplicate id {dup}" for dup in diag["duplicateIds"]]
    if diag["horizontalScroll"]:
        problems.append(
            f"{label}: horizontal scroll ({diag['scrollWidth']} > {diag['innerWidth']}), "
            f"first overflowing: {diag['overflowing']}"
        )
    return problems


@dataclass
class Outcome:
    control: Control
    via: str | None
    problems: list[str] = field(default_factory=list)
    skipped: str | None = None
    new_controls: list[Control] = field(default_factory=list)


def _signature(page: Page) -> dict[str, Any]:
    for _ in range(5):
        try:
            return dict(page.evaluate(SIGNATURE_JS))
        except PlaywrightError:  # navigation in flight: execution context destroyed
            settle(page)
    return dict(page.evaluate(SIGNATURE_JS))


def restore_db(snapshot: Path, live: Path) -> None:
    """Copy the pristine snapshot over the live scratch DB (sqlite backup API)."""
    src = sqlite3.connect(snapshot.as_posix())
    dst = sqlite3.connect(live.as_posix(), timeout=10)
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def _check_download(page: Page, base_url: str, control: Control) -> list[str]:
    url = urljoin(base_url + "/", control.target)
    resp = page.context.request.get(url)
    return [] if resp.ok else [f"download {url} -> HTTP {resp.status}"]


def activate(
    page: Page,
    recorder: Recorder,
    *,
    base_url: str,
    route: str,
    control: Control,
    via: Control | None,
    on_destructive: Callable[[], None],
) -> Outcome:
    """Load ``route`` fresh, (optionally open ``via``), activate ``control``."""
    outcome = Outcome(control=control, via=via.name if via else None)
    reason = skip_reason(control)
    if reason:
        outcome.skipped = reason
        return outcome
    mutates = control.destructive or (via is not None and via.destructive)
    if mutates:
        on_destructive()
    page.goto(base_url + route)
    settle(page)
    recorder.drain()
    if via is not None:
        opener = element_for(page, via)
        if opener is None:
            outcome.problems.append(f"parent control {via.key} not found on reload")
            return outcome
        opener.click()
        settle(page)
        recorder.drain()
    el = element_for(page, control)
    if el is None:
        outcome.problems.append("control not found after reload")
        return outcome
    if control.download:
        outcome.problems += _check_download(page, base_url, control)
        return outcome
    before_keys = {c.key for c in find_controls(page)}
    before = _signature(page)
    try:
        el.click(no_wait_after=True, timeout=CLICK_TIMEOUT_MS)
    except PlaywrightError as exc:
        outcome.problems.append(f"not clickable: {str(exc).splitlines()[0]}")
        return outcome
    settle(page)
    after = _signature(page)
    outcome.problems += recorder.drain()
    outcome.problems += diagnose(page, "after control")
    changed = (
        before["url"] != after["url"]
        or before["hash"] != after["hash"]
        or before["dialogs"] != after["dialogs"]
        or before["expanded"] != after["expanded"]
        or before["htmxDone"] != after["htmxDone"]
        or (control.kind == "link" and control.target == before["url"])
        or (control.kind == "link" and urlparse(control.target).path == urlparse(route).path)
    )
    if after["htmxBusy"]:
        outcome.problems.append("htmx request still in flight after 4s")
    if not changed and not control.invalid:
        outcome.problems.append("control did nothing (no navigation, swap, open or close)")
    if mutates:
        on_destructive()
    if before["url"] == after["url"]:
        outcome.new_controls = [c for c in stable_controls(page) if c.key not in before_keys]
    return outcome


def path_of(route: str) -> str:
    return urlparse(route).path
