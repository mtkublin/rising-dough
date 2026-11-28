"""Server-side resolver: evaluate a UI-map ``Locator`` over BeautifulSoup.

Mirrors Playwright's ``get_by_role`` / ``get_by_label`` / id queries closely
enough for the markup the app renders: implicit ARIA roles for common
elements, accessible name from ``aria-labelledby``, ``aria-label``,
``<label>``, then text content (``alt`` / ``title`` / ``value`` fallbacks).
Name matching is a case-insensitive substring unless ``exact=True``.

Entry points: ``resolve(html_or_soup, locator) -> list[Tag]``,
``resolve_one`` (exactly one), ``exists`` / ``count`` / ``text_of``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from bs4 import BeautifulSoup, Tag

from tests.ui_map.locator import Locator, NameMatcher

Source = str | BeautifulSoup | Tag

_INPUT_ROLES = {
    "button": "button",
    "submit": "button",
    "reset": "button",
    "image": "button",
    "checkbox": "checkbox",
    "radio": "radio",
    "range": "slider",
    "number": "spinbutton",
    "search": "searchbox",
    "email": "textbox",
    "tel": "textbox",
    "url": "textbox",
    "text": "textbox",
}
_NAME_CHILD = {"table": "caption", "fieldset": "legend"}  # element -> child that names it
_STATIC_ROLES = {
    "a": "link",
    "button": "button",
    "dialog": "dialog",
    "nav": "navigation",
    "main": "main",
    "aside": "complementary",
    "form": "form",
    "table": "table",
    "tr": "row",
    "td": "cell",
    "th": "columnheader",
    "ul": "list",
    "ol": "list",
    "li": "listitem",
    "dt": "term",
    "dd": "definition",
    "textarea": "textbox",
    "img": "img",
    "progress": "progressbar",
    "output": "status",
    "option": "option",
    "summary": "button",
    "fieldset": "group",
    "hr": "separator",
}
_HEADING = re.compile(r"^h([1-6])$")
_NAME_FROM_CONTENT = {
    "button", "link", "heading", "cell", "columnheader", "rowheader",
    "row", "option", "listitem", "tab", "menuitem", "checkbox", "radio",
    "switch", "status", "alert", "caption",
}  # fmt: skip
_WS = re.compile(r"\s+")


def _soup(source: Source) -> BeautifulSoup | Tag:
    return BeautifulSoup(source, "html.parser") if isinstance(source, str) else source


def _norm(text: str) -> str:
    return _WS.sub(" ", text).strip()


def implicit_role(el: Tag) -> str | None:  # noqa: PLR0911
    """Explicit ``role`` attribute, else the element's implicit ARIA role."""
    explicit = el.get("role")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.split()[0]
    tag = el.name
    if _HEADING.match(tag):
        return "heading"
    if tag == "input":
        kind = str(el.get("type", "text")).lower()
        if kind == "hidden":
            return None
        if kind == "text" and el.get("list"):
            return "combobox"
        return _INPUT_ROLES.get(kind)
    if tag == "select":
        multiple = el.has_attr("multiple") or int(str(el.get("size", "1")) or 1) > 1
        return "listbox" if multiple else "combobox"
    if tag == "a":
        return "link" if el.has_attr("href") else None
    if tag == "section":
        return "region" if (el.get("aria-label") or el.get("aria-labelledby")) else None
    if tag == "form":
        return "form" if (el.get("aria-label") or el.get("aria-labelledby")) else None
    if tag == "header":
        return None if el.find_parent(["article", "section", "main"]) else "banner"
    if tag == "footer":
        return None if el.find_parent(["article", "section", "main"]) else "contentinfo"
    return _STATIC_ROLES.get(tag)


def _visible_text(el: Tag) -> str:
    return _norm(el.get_text(" "))


def _by_id(el: Tag, ident: str) -> Tag | None:
    root = el.find_parent(lambda t: t.parent is None) or el
    found = root.find(id=ident) if isinstance(root, Tag) else None
    return found if isinstance(found, Tag) else None


def accessible_name(el: Tag) -> str:  # noqa: PLR0911
    """Approximation of the accessible-name computation for common cases."""
    labelledby = el.get("aria-labelledby")
    if isinstance(labelledby, str):
        parts = [_by_id(el, i) for i in labelledby.split()]
        joined = " ".join(_visible_text(p) for p in parts if p is not None)
        if joined.strip():
            return _norm(joined)
    aria = el.get("aria-label")
    if isinstance(aria, str) and aria.strip():
        return _norm(aria)
    labelled = _label_text(el)
    if labelled:
        return labelled
    role = implicit_role(el)
    if el.name == "input" and role == "button":
        value = el.get("value") or ("Submit" if el.get("type") == "submit" else "")
        return _norm(str(value))
    if el.name == "img" or el.get("type") == "image":
        alt = el.get("alt")
        if isinstance(alt, str):
            return _norm(alt)
    if role in _NAME_FROM_CONTENT or el.name == "summary":
        text = _visible_text(el)
        if text:
            return text
    named_by = _NAME_CHILD.get(el.name)
    child = el.find(named_by) if named_by else None
    if isinstance(child, Tag):
        return _visible_text(child)
    title = el.get("title")
    return _norm(title) if isinstance(title, str) else ""


def _labels_for(el: Tag) -> list[Tag]:
    labels: list[Tag] = []
    ident = el.get("id")
    root = el.find_parent(lambda t: t.parent is None) or el
    if isinstance(ident, str) and ident and isinstance(root, Tag):
        labels.extend(root.find_all("label", attrs={"for": ident}))
    wrapping = el.find_parent("label")
    if isinstance(wrapping, Tag):
        labels.append(wrapping)
    return labels


def _label_text(el: Tag) -> str:
    if el.name not in {"input", "select", "textarea", "button", "meter", "output"}:
        return ""
    if el.name == "input" and str(el.get("type", "")).lower() == "hidden":
        return ""
    texts = []
    for lab in _labels_for(el):
        clone = BeautifulSoup(str(lab), "html.parser")
        for inner in clone.find_all(["input", "select", "textarea"]):
            inner.decompose()
        texts.append(_visible_text(clone))
    return _norm(" ".join(t for t in texts if t))


def _matches(actual: str, wanted: NameMatcher, *, exact: bool) -> bool:
    if isinstance(wanted, re.Pattern):
        return wanted.search(actual) is not None
    if exact:
        return _norm(actual) == _norm(wanted)
    return _norm(wanted).lower() in actual.lower()


def _is_hidden(el: Tag) -> bool:
    for node in (el, *el.parents):
        if node.has_attr("hidden") or node.get("aria-hidden") == "true":
            return True
        style = str(node.get("style", "")).replace(" ", "").lower()
        if "display:none" in style:
            return True
    return False


def _descendants(scope: Tag | BeautifulSoup) -> Iterator[Tag]:
    return (d for d in scope.descendants if isinstance(d, Tag))


def _candidates(scopes: list[Tag | BeautifulSoup], loc: Locator) -> list[Tag]:
    found: list[Tag] = []
    seen: set[int] = set()  # identity, not Tag equality (equal markup != same node)
    for scope in scopes:
        for el in _descendants(scope):
            if id(el) not in seen and _match_one(el, loc):
                seen.add(id(el))
                found.append(el)
    return found


def _match_one(el: Tag, loc: Locator) -> bool:  # noqa: PLR0911
    if loc.kind == "id":
        ident = el.get("id")
        if not isinstance(ident, str):
            return False
        return ident.startswith(loc.value) if loc.id_prefix else ident == loc.value
    if loc.kind == "testid":
        return el.get("data-testid") == loc.value
    if loc.kind == "label":
        by_label = _is_labelable(el) and any(
            _matches(_norm(_visible_text_without_controls(lab)), loc.value, exact=loc.exact)
            for lab in _labels_for(el)
        )
        return by_label or _aria_label_matches(el, loc) or _aria_labelledby_matches(el, loc)
    # role
    if _is_hidden(el) or implicit_role(el) != loc.value:
        return False
    if loc.level is not None:
        m = _HEADING.match(el.name)
        level = int(m.group(1)) if m else int(str(el.get("aria-level", "0")) or 0)
        if level != loc.level:
            return False
    if loc.pressed is not None and (el.get("aria-pressed") == "true") != loc.pressed:
        return False
    if loc.name is None:
        return True
    return _matches(accessible_name(el), loc.name, exact=loc.exact)


def _visible_text_without_controls(lab: Tag) -> str:
    clone = BeautifulSoup(str(lab), "html.parser")
    for inner in clone.find_all(["input", "select", "textarea"]):
        inner.decompose()
    return _visible_text(clone)


_LABELABLE = {"select", "textarea", "button", "meter", "output", "progress"}


def _is_labelable(el: Tag) -> bool:
    """HTML labelable elements (what a ``<label>`` can actually label)."""
    if el.name == "input":
        return str(el.get("type", "")).lower() != "hidden"
    return el.name in _LABELABLE


def _aria_labelledby_matches(el: Tag, loc: Locator) -> bool:
    ids = el.get("aria-labelledby")
    if not isinstance(ids, str):
        return False
    parts = [_by_id(el, i) for i in ids.split()]
    text = " ".join(_visible_text(p) for p in parts if p is not None)
    return bool(text.strip()) and _matches(_norm(text), loc.value, exact=loc.exact)


def _aria_label_matches(el: Tag, loc: Locator) -> bool:
    aria = el.get("aria-label")
    return isinstance(aria, str) and _matches(aria, loc.value, exact=loc.exact)


def resolve(source: Source, loc: Locator) -> list[Tag]:
    """All elements matching ``loc`` (document order), honouring ``within``."""
    root = _soup(source)
    scopes: list[Tag | BeautifulSoup] = [root]
    if loc.within is not None:
        scopes = list(resolve(root, loc.within))
    return _candidates(scopes, loc)


def resolve_one(source: Source, loc: Locator) -> Tag:
    found = resolve(source, loc)
    if len(found) != 1:
        raise LookupError(f"expected exactly one match for {loc!r}, found {len(found)}")
    return found[0]


def count(source: Source, loc: Locator) -> int:
    return len(resolve(source, loc))


def exists(source: Source, loc: Locator) -> bool:
    return count(source, loc) > 0


def text_of(source: Source, loc: Locator) -> str:
    """Normalised text content of the single match."""
    return _visible_text(resolve_one(source, loc))


def all_text(source: Source, loc: Locator) -> str:
    """Normalised text of every match, joined with a space (empty when none)."""
    return _norm(" ".join(_visible_text(el) for el in resolve(source, loc)))


def page_text(source: Source) -> str:
    """Normalised visible text of the whole document (no markup, no attributes)."""
    return _norm(_soup(source).get_text(" "))


def document_title(source: Source) -> str:
    """Normalised ``<title>`` text (empty when the document has none)."""
    title = _soup(source).find("title")
    return _visible_text(title) if isinstance(title, Tag) else ""


def form_of(source: Source, loc: Locator) -> Tag:
    """The ``<form>`` that is (or contains) the single match of ``loc``."""
    el = resolve_one(source, loc)
    form = el if el.name == "form" else el.find_parent("form")
    if not isinstance(form, Tag):
        raise LookupError(f"{loc!r} is not inside a form")
    return form


def submitted_fields(form: Tag) -> list[tuple[str, str]]:
    """``(name, value)`` pairs the browser would submit for ``form`` as rendered.

    Mirrors HTML successful-controls: disabled and nameless controls are skipped,
    checkboxes and radios only when checked, selects by their selected option.
    """
    fields: list[tuple[str, str]] = []
    for el in form.find_all(["input", "select", "textarea"]):
        name = el.get("name")
        if not isinstance(name, str) or el.has_attr("disabled"):
            continue
        kind = str(el.get("type", "text")).lower()
        if el.name == "input" and kind in {"checkbox", "radio"} and not el.has_attr("checked"):
            continue
        if el.name == "input" and kind in {"submit", "button", "image", "reset", "file"}:
            continue
        if el.name == "textarea":
            fields.append((name, el.get_text()))
        elif el.name == "select":
            chosen = el.find("option", selected=True) or el.find("option")
            if isinstance(chosen, Tag):
                fields.append((name, str(chosen.get("value", chosen.get_text(strip=True)))))
        else:
            fields.append(
                (name, str(el.get("value", "on" if kind in {"checkbox", "radio"} else "")))
            )
    return fields


def texts(source: Source, loc: Locator) -> list[str]:
    """Normalised text of every match, in document order."""
    return [_visible_text(el) for el in resolve(source, loc)]


def error_lines(source: Source) -> dict[str, str]:
    """Every visible error line of a failed save (Q18, no summary box), keyed by element id.

    Each ``<p>`` reading ``▲ <message>``: the per-field ``field-<name>-error``, the hero error, the
    category picker's, and the dialog-level ``dialog-error-<name>`` (an error with no field line).
    """
    lines: dict[str, str] = {}
    for el in _descendants(_soup(source)):
        text = _norm(el.get_text())
        if el.name == "p" and text.startswith("\u25b2 "):
            lines[str(el.get("id", f"(no id) {text}"))] = text
    return lines


def is_fragment(source: Source) -> bool:
    """True when ``source`` is a bare fragment (no ``<html>`` document element)."""
    return _soup(source).find("html") is None
