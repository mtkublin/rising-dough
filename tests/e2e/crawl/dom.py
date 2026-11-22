# ruff: noqa: E501
"""In-page JavaScript used by the crawler, plus the Python-side result types.

All DOM access is through ``page.evaluate`` / element handles so the
crawler never uses CSS locators (ADR-0106 section 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Final

# One query, one order: the crawler re-finds controls by (kind, name, target)
# against a fresh run of this same function, so keep it deterministic.
_COLLECT_JS: Final = r"""
() => {
  const SEL = [
    'a[href]', 'button', 'input[type=submit]', 'input[type=button]', 'summary',
    '[hx-get]', '[hx-post]', '[hx-put]', '[hx-patch]', '[hx-delete]',
    '[role=menuitem]', '[role=button]', '[role=tab]', '[popovertarget]',
    '[aria-haspopup]',
  ].join(',');
  const visible = (el) => {
    const closed = el.closest('details:not([open])');
    if (closed && el.tagName.toLowerCase() !== 'summary' && !(el.closest('summary'))) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  const collapse = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const nameOf = (el) => {
    const lab = el.getAttribute('aria-label');
    if (lab) return collapse(lab);
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = by.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean)
        .map(n => n.textContent).join(' ');
      if (collapse(t)) return collapse(t);
    }
    const txt = collapse(el.textContent);
    if (txt) return txt.length > 60 ? txt.slice(0, 60) + '...' : txt;
    return collapse(el.getAttribute('title') || el.getAttribute('value') || '');
  };
  const seen = new Set();
  const out = [];
  for (const el of document.querySelectorAll(SEL)) {
    if (seen.has(el)) continue;
    seen.add(el);
    if (!visible(el)) continue;
    const tag = el.tagName.toLowerCase();
    const form = el.closest('form');
    const verbs = ['hx-get', 'hx-post', 'hx-put', 'hx-patch', 'hx-delete'];
    let verb = verbs.find(v => el.hasAttribute(v)) || null;
    let target = verb ? el.getAttribute(verb) : null;
    let kind;
    if (verb) kind = verb;
    else if (tag === 'a') { kind = 'link'; target = el.getAttribute('href'); }
    else if (el.hasAttribute('popovertarget')) { kind = 'popover'; target = '#' + el.getAttribute('popovertarget'); }
    else if (tag === 'summary') kind = 'disclosure';
    else if (el.getAttribute('role') === 'menuitem') kind = 'menuitem';
    else if (el.getAttribute('role') === 'tab') kind = 'tab';
    else kind = 'button';
    const isSubmit = (tag === 'button' && (el.getAttribute('type') || 'submit') === 'submit')
      || (tag === 'input' && el.type === 'submit');
    if (!target && isSubmit && form) {
      target = form.getAttribute('hx-post') || form.getAttribute('action') || '';
      if (form.hasAttribute('hx-post') || (form.method || 'get').toLowerCase() === 'post') kind = 'submit';
      else kind = 'submit-get';
    }
    if (!target && el.hasAttribute('aria-controls')) target = '#' + el.getAttribute('aria-controls');
    const hxForm = form && (form.hasAttribute('hx-post') || form.hasAttribute('hx-delete'));
    const destructive = ['hx-post', 'hx-put', 'hx-patch', 'hx-delete', 'submit'].includes(kind)
      || (isSubmit && hxForm);
    const shell = !!el.closest('header, nav, aside, footer, [role=navigation]');
    out.push({el, meta: {
      kind, name: nameOf(el), target: target || '',
      destructive, shell,
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      download: el.hasAttribute('download'),
      external: tag === 'a' && el.origin !== location.origin,
      blank: el.getAttribute('target') === '_blank',
      invalid: !!(form && isSubmit && !form.checkValidity()),
      nonclick: ['form', 'input', 'select', 'textarea'].includes(tag) && !isSubmit && el.type !== 'button'
        || (verb !== null && !['a', 'button', 'input', 'summary'].includes(tag) && !el.getAttribute('role')),
      offscreen: (() => { const r = el.getBoundingClientRect(); return r.right <= 0 || r.bottom <= 0 || r.left >= window.innerWidth || r.width <= 1 || r.height <= 1; })(),
    }});
  }
  RETURN
}
"""

FIND_CONTROLS_JS: Final = _COLLECT_JS.replace("RETURN", "return out.map(o => o.meta);")
CONTROL_ELEMENTS_JS: Final = _COLLECT_JS.replace("RETURN", "return out.map(o => o.el);")

HTMX_COUNTER_JS: Final = """
document.addEventListener('htmx:afterRequest', () => {
  window.__crawlHtmxDone = (window.__crawlHtmxDone || 0) + 1;
});
"""

SIGNATURE_JS: Final = r"""
() => {
  const html = (document.body ? document.body.outerHTML : '').replace(/\s+/g, ' ');
  let h = 5381;
  for (let i = 0; i < html.length; i++) h = ((h * 33) ^ html.charCodeAt(i)) >>> 0;
  return {
    url: location.pathname + location.search + location.hash,
    hash: h,
    dialogs: document.querySelectorAll('dialog[open], [popover]:popover-open').length,
    expanded: document.querySelectorAll('[aria-expanded=true]').length,
    htmxDone: window.__crawlHtmxDone || 0,
    htmxBusy: document.querySelectorAll('.htmx-request, .htmx-swapping, .htmx-settling').length,
  };
}
"""

DIAGNOSTICS_JS: Final = r"""
() => {
  const seen = new Map();
  document.querySelectorAll('[id]').forEach(e => seen.set(e.id, (seen.get(e.id) || 0) + 1));
  const dup = [...seen.entries()].filter(([, n]) => n > 1).map(([id, n]) => `${id} x${n}`).sort();
  const over = [...document.querySelectorAll('body *')]
    .filter(el => el.getBoundingClientRect().right > window.innerWidth + 1)
    .slice(0, 3)
    .map(el => `${el.tagName.toLowerCase()}#${el.id || ''}`);
  return {
    horizontalScroll: document.documentElement.scrollWidth > window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    overflowing: over,
    duplicateIds: dup,
  };
}
"""

_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_MONTH = re.compile(r"\d{4}-\d{2}(?!\d)")
_MONTH_YEAR = re.compile(rf"{_MONTHS}\.? \d{{4}}")
_DAY_MONTH = re.compile(rf"\b\d{{1,2}} {_MONTHS}\b|\b{_MONTHS} \d{{1,2}}\b")
_HANDLE = re.compile(r"/sessions/[0-9a-f]{16}")
_PATH_ID = re.compile(r"/\d+(?=/|$|\?)")
_QUERY_NUM = re.compile(r"=\d+(?=&|$)")


def normalise_target(target: str) -> str:
    """Replace ids and dates so the committed inventory is stable over time."""
    out = _DATE.sub("{date}", target)
    out = _HANDLE.sub("/sessions/{handle}", out)
    out = _MONTH.sub("{month}", out)
    out = _PATH_ID.sub("/{id}", out)
    return _QUERY_NUM.sub("={n}", out)


def normalise_name(name: str) -> str:
    out = _DATE.sub("{date}", name)
    out = _MONTH_YEAR.sub("{month}", out)
    return _DAY_MONTH.sub("{day}", out)


@dataclass(frozen=True)
class Control:
    kind: str
    name: str
    target: str
    destructive: bool
    shell: bool
    disabled: bool
    download: bool
    external: bool
    blank: bool
    invalid: bool
    nonclick: bool
    offscreen: bool

    @classmethod
    def from_js(cls, raw: dict[str, Any]) -> Control:
        return cls(**{k: raw[k] for k in cls.__dataclass_fields__})

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.kind, self.name, self.target)

    def inventory(self, via: str | None = None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "kind": self.kind,
            "name": normalise_name(self.name),
            "target": normalise_target(self.target),
        }
        if self.destructive:
            entry["destructive"] = True
        if via is not None:
            entry["via"] = via
        return entry
