"""Locator description shared by Playwright and the server-side resolver.

A ``Locator`` is a frozen, engine-neutral description of "which element".
``tests.ui_map._html.resolve`` evaluates it over BeautifulSoup;
``to_playwright`` turns the same value into Playwright calls. Kinds, in
order of preference (ADR-0106 section 2): ``role`` (+ accessible name),
``label``, ``id``, ``testid`` (last resort). CSS classes are not allowed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Literal

Kind = Literal["role", "label", "id", "testid"]
NameMatcher = str | re.Pattern[str]


@dataclass(frozen=True)
class Locator:
    kind: Kind
    value: str  # ARIA role, label text, element id or test id
    name: NameMatcher | None = None  # accessible name (role only)
    level: int | None = None  # heading level (role=heading only)
    exact: bool = False  # exact (case-sensitive, full) name/label match
    id_prefix: bool = False  # id kind: match ids starting with ``value``
    within: Locator | None = None  # scope: search inside this locator's match

    def inside(self, scope: Locator) -> Locator:
        """Return a copy scoped to ``scope`` (outermost scope wins)."""
        if self.within is not None:
            return replace(self, within=self.within.inside(scope))
        return replace(self, within=scope)


def role(
    role_name: str,
    name: NameMatcher | None = None,
    *,
    level: int | None = None,
    exact: bool = False,
) -> Locator:
    return Locator("role", role_name, name=name, level=level, exact=exact)


def label(text: str, *, exact: bool = False) -> Locator:
    return Locator("label", text, exact=exact)


def by_id(element_id: str, *, prefix: bool = False) -> Locator:
    return Locator("id", element_id, id_prefix=prefix)


def by_testid(value: str) -> Locator:
    """Last resort: only where role / label / id are ambiguous."""
    return Locator("testid", value)


def _css_id(value: str, prefix: bool) -> str:
    op = "^=" if prefix else "="
    return f'[id{op}"{value}"]'


def to_playwright(root: Any, loc: Locator) -> Any:
    """Resolve ``loc`` against a Playwright ``Page`` / ``Locator`` (duck-typed)."""
    scope = root if loc.within is None else to_playwright(root, loc.within)
    if loc.kind == "role":
        kwargs: dict[str, Any] = {"exact": loc.exact}
        if loc.name is not None:
            kwargs["name"] = loc.name
        if loc.level is not None:
            kwargs["level"] = loc.level
        return scope.get_by_role(loc.value, **kwargs)
    if loc.kind == "label":
        return scope.get_by_label(loc.value, exact=loc.exact)
    if loc.kind == "testid":
        return scope.get_by_test_id(loc.value)
    return scope.locator(_css_id(loc.value, loc.id_prefix))
