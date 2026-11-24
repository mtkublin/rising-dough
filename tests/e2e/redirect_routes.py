"""Shared by the advisory sweeps (axe, Lighthouse): name redirect-only routes, do not scan them.

A legacy route that 3xx-redirects (``/auth/sessions`` and ``/settings/password`` ->
``/settings/security``) is never the page a sweep sees; it only repeats the target. Such routes are
excluded by name (T-Q322 follow-up (f), OPS-2, OPS-7).
"""

from __future__ import annotations

from collections.abc import Sequence

from playwright.sync_api import APIRequestContext


def split_redirect_routes(statuses: dict[str, int]) -> tuple[list[str], list[str]]:
    """Split routes into (measurable, redirect-only) by their un-followed GET status."""
    redirected = [r for r, status in statuses.items() if 300 <= status < 400]
    return [r for r in statuses if r not in redirected], redirected


def probe_routes(
    request: APIRequestContext, base_url: str, routes: Sequence[str]
) -> tuple[list[str], list[str]]:
    """GET each route without following redirects, then split (measurable, redirect-only)."""
    statuses = {r: request.get(base_url + r, max_redirects=0).status for r in routes}
    return split_redirect_routes(statuses)
