"""Generated crawler smoke test (T-UT07, ADR-0106 section 3).

One test per page route. Each logs in on a seeded scratch DB, discovers every
control (link, button, ``hx-*``, menu item, dialog / popover trigger), activates
each one and asserts: no 4xx/5xx, no console errors, no failed requests, no
duplicate ids, no horizontal scroll at 375, 1024 and 1440, and that the control did
something (navigated, opened, closed or swapped). Destructive controls
(POST / delete) run after the scratch DB is restored from a pristine snapshot.

The discovered inventory must match ``crawl_inventory.json``; regenerate with
``CRAWL_UPDATE=1`` and review the diff as a UI change.

Themes: the app ships a single theme (no ``data-theme`` / dark-mode CSS), so
the crawl runs once. Revisit when the redesign adds a second theme.

Only the 1440 viewport activates controls (several are hidden at 375);
375 and 1024 get the load-time diagnostics (T-Q301: the
frontend-visual-audit viewport set).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from budget_planner.web.app import app
from tests.e2e.crawl import inventory
from tests.e2e.crawl.dom import Control
from tests.e2e.crawl.engine import (
    DESKTOP,
    MOBILE,
    TABLET,
    Recorder,
    activate,
    diagnose,
    find_controls,
    restore_db,
    settle,
    skip_reason,
)
from tests.e2e.crawl.seed import SeedIds, seed_world

pytestmark = pytest.mark.e2e

# Full-page GET routes. ``{account_id}`` is filled from the seed.
PAGES: tuple[str, ...] = (
    "/accounts",
    "/auth/sessions",
    "/budget",
    "/forecast",
    "/ledger",
    "/ledger/recently-deleted",
    "/plan",
    "/settings",
    "/settings/password",
    "/settings/security",
    "/settings/users",
    "/today",
)

# Extra tab views of a page route, crawled as pages in their own right. A view
# is a query-string variant users open; its path must be in PAGES.
VIEWS: tuple[str, ...] = ("/plan?tab=year",)

# GET routes deliberately not crawled as pages: htmx fragments, forms opened
# from a page control (reached through that control), downloads, and auth
# flows. ``test_every_get_route_is_classified`` keeps this list honest.
NOT_PAGES: dict[str, str] = {
    "/accounts/{account_id}/reconcile": "dialog fragment (no base template, no htmx)",
    "/add": "overlay fragment (no base template, no htmx)",
    "/accounts/new": "dialog fragment",
    "/accounts/{account_id}/edit": "dialog fragment",
    "/auth/login": "login form (crawl starts logged in)",
    "/auth/reauth": "re-auth form",
    "/auth/register": "WebAuthn registration",
    "/budget/yearly": "fragment (host page: /plan?tab=year, crawled in VIEWS)",
    "/budget/rules/{category_id}/overrides/new": "dialog fragment",
    "/categories/new": "dialog fragment",
    "/categories/{category_id}/archive": "dialog fragment",
    "/categories/{category_id}/edit": "dialog fragment",
    "/forecast/view": "fragment",
    "/ledger/table": "fragment",
    "/planned/export": "download",
    "/planned/new": "dialog fragment",
    "/planned/table": "fragment",
    "/planned/{planned_id}/edit": "dialog fragment",
    "/planned/{planned_id}/promote": "dialog fragment",
    "/recurring/new": "dialog fragment",
    "/recurring/{rule_id}/edit": "dialog fragment",
    "/recurring/{rule_id}/overrides/new": "dialog fragment",
    "/recurring/{rule_id}/promote": "dialog fragment",
    "/settings/close": "fragment",
    "/settings/users/{user_id}/delete": "dialog fragment",
    "/settings/users/{user_id}/edit": "dialog fragment",
    "/settings/users/{user_id}/reset-password": "dialog fragment",
    # one-time token in the query; closed → 303 /auth/login (T-UR21, ADR-0134 §9)
    "/setup": "one-time token in the query; closed → 303 /auth/login (T-UR21, ADR-0134 §9)",
    "/today/afford": "fragment",
    "/today/upcoming": "fragment",
    "/transactions": "legacy list route (redirects into /ledger)",
    "/transactions/_limit_preview": "fragment",
    "/transactions/export": "download",
    "/transactions/new": "dialog fragment",
    "/transactions/table": "fragment",
    "/transactions/{txn_id}/edit": "dialog fragment",
}

# Real app bugs found by the crawl (not fixed here, ADR-0106 / T-UT07 notes).
# (Empty today: T-D-UT07-1 was a crawler artefact, see docs/audits/2026-11-21-plan-year-crawl.md.)
# route -> (task id, substring identifying the problem, reason). The page test
# ignores matching problems; ``test_known_bug`` re-crawls and xfails strictly,
# so the day the bug is fixed the xfail turns into a failure and the entry must go.
KNOWN_BUGS: dict[str, tuple[str, str, str]] = {}

# Shell controls (header / nav / aside / footer) are identical on every page;
# activate each once per run and only list them per page. Serial-run state.
_SHELL_DONE: set[tuple[str, str, str]] = set()


@pytest.fixture
def crawl_env(
    live_server: tuple[str, Path], page: Page, tmp_path: Path
) -> tuple[str, Path, Path, SeedIds]:
    base_url, db_path = live_server
    ids = seed_world(page.request, base_url, db_path)
    snapshot = tmp_path / "pristine.sqlite"
    restore_db(db_path, snapshot)  # backup live -> snapshot (same API, either direction)
    return base_url, db_path, snapshot, ids


def _resolve(route: str, ids: SeedIds) -> str:
    return route.format(account_id=ids.account_id)


def crawl_page(
    page: Page,
    *,
    base_url: str,
    route_template: str,
    route: str,
    on_destructive: Any,
    shell_done: set[tuple[str, str, str]],
    activate_controls: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (inventory entries, problems) for one page."""
    recorder = Recorder(page, base_url)
    problems: list[str] = []

    page.set_viewport_size(MOBILE)  # type: ignore[arg-type]
    page.goto(base_url + route)
    settle(page)
    problems += [f"[load 375] {p}" for p in recorder.drain()]
    problems += diagnose(page, "[375]")

    page.set_viewport_size(TABLET)  # type: ignore[arg-type]
    page.goto(base_url + route)
    settle(page)
    problems += [f"[load 1024] {p}" for p in recorder.drain()]
    problems += diagnose(page, "[1024]")

    page.set_viewport_size(DESKTOP)  # type: ignore[arg-type]
    page.goto(base_url + route)
    settle(page)
    problems += [f"[load 1440] {p}" for p in recorder.drain()]
    problems += diagnose(page, "[1440]")

    if not activate_controls:
        return [], problems
    entries: list[dict[str, Any]] = []
    top = find_controls(page)
    queue: list[tuple[Control, Control | None]] = [(c, None) for c in top]
    seen: set[tuple[str, str, str, str]] = set()
    while queue:
        control, via = queue.pop(0)
        ident = (via.name if via else "", *control.key)
        # Children of shell controls (the Add dialog, ...) are crawled once per
        # run but not inventoried per page: whether a page activates the shell
        # control depends on run order, and the inventory must not.
        if via is None or not via.shell:
            entry = control.inventory(via.name if via else None)
            reason = skip_reason(control)
            if reason:
                entry["skipped"] = reason
            entries.append(entry)
        if ident in seen:
            continue
        seen.add(ident)
        if control.shell and via is None:
            if control.key in shell_done:
                continue
            shell_done.add(control.key)
        outcome = activate(
            page,
            recorder,
            base_url=base_url,
            route=route,
            control=control,
            via=via,
            on_destructive=on_destructive,
        )
        label = f"{route} :: {control.kind} {control.name!r} -> {control.target!r}"
        if via is not None:
            label += f" (via {via.name!r})"
        problems += [f"{label}: {p}" for p in outcome.problems]
        if via is None:  # one level of children: menu items, dialog buttons
            queue += [(child, control) for child in outcome.new_controls]
    return inventory.canonical(entries), problems


@pytest.mark.parametrize(
    "route_template", (*PAGES, *VIEWS), ids=lambda r: r.strip("/").replace("/", "_")
)
def test_crawl_page(
    route_template: str,
    page: Page,
    crawl_env: tuple[str, Path, Path, SeedIds],
) -> None:
    base_url, db_path, snapshot, ids = crawl_env
    route = _resolve(route_template, ids)
    entries, problems = crawl_page(
        page,
        base_url=base_url,
        route_template=route_template,
        route=route,
        on_destructive=lambda: restore_db(snapshot, db_path),
        shell_done=_SHELL_DONE,
    )
    committed = inventory.load()
    if inventory.updating():
        committed[route_template] = entries
        inventory.store(committed)
    else:
        drift = inventory.diff(committed.get(route_template, []), entries)
        if drift:
            problems.append(
                f"inventory drift for {route_template} (regenerate with CRAWL_UPDATE=1):\n"
                + "\n".join(drift)
            )
    known = KNOWN_BUGS.get(route_template)
    if known:
        problems = [p for p in problems if known[1] not in p]
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "route_template",
    [
        pytest.param(
            route,
            marks=pytest.mark.xfail(strict=True, reason=f"{task}: {reason}"),
            id=route.strip("/").replace("/", "_"),
        )
        for route, (task, _needle, reason) in KNOWN_BUGS.items()
    ],
)
def test_known_bug(
    route_template: str,
    page: Page,
    crawl_env: tuple[str, Path, Path, SeedIds],
) -> None:
    base_url, db_path, snapshot, ids = crawl_env
    _entries, problems = crawl_page(
        page,
        base_url=base_url,
        route_template=route_template,
        route=_resolve(route_template, ids),
        on_destructive=lambda: restore_db(snapshot, db_path),
        shell_done=set(),
    )
    needle = KNOWN_BUGS[route_template][1]
    assert not [p for p in problems if needle in p]


def test_inventory_covers_exactly_the_pages() -> None:
    if inventory.updating():
        pytest.skip("regenerating")
    stale = sorted(set(inventory.load()) - {*PAGES, *VIEWS})
    missing = sorted({*PAGES, *VIEWS} - set(inventory.load()))
    assert not stale and not missing, f"inventory stale: {stale}, missing: {missing}"


def test_every_get_route_is_classified() -> None:
    """A new page must be added to PAGES (crawled) or NOT_PAGES (with a reason)."""
    get_paths = {p for p, ops in app.openapi()["paths"].items() if "get" in ops}
    assert all(v.split("?")[0] in PAGES for v in VIEWS)
    known = set(PAGES) | set(NOT_PAGES)
    assert not (get_paths - known), f"unclassified GET routes: {sorted(get_paths - known)}"
    assert not (known - get_paths), f"classified but not in the app: {sorted(known - get_paths)}"
