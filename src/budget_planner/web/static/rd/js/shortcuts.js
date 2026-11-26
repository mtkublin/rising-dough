/*
 * Global keyboard shortcuts. Targets are declared in markup with aria-keyshortcuts, so the map lives
 * in the templates (and is announced to assistive tech): g o / g l / g p / g a / g s, n, ?.
 * Extra: / focuses the page's search or filter, [ and ] cycle the ledger/plan/settings tabs.
 * Ignored while typing in a field or while a modal is open (except Esc, which is native).
 */
(() => {
  let pending = '';
  let timer = 0;

  function typing(target) {
    return target.closest('input, textarea, select, [contenteditable="true"]');
  }

  function activate(el) {
    if (el.hasAttribute('hx-get')) el.click();
    else if (el.tagName === 'A') window.location.assign(el.href);
    else el.click();
  }

  function byKeys(keys) {
    return [...document.querySelectorAll('[aria-keyshortcuts]')].find((el) => {
      const list = el.getAttribute('aria-keyshortcuts').split(/\s*,\s*|\s{2,}/);
      return list.includes(keys) && el.getClientRects().length > 0;
    }) || [...document.querySelectorAll('[aria-keyshortcuts]')].find((el) => el.getAttribute('aria-keyshortcuts') === keys);
  }

  function cycleTabs(dir) {
    const tabs = [...document.querySelectorAll('.rd-tabs:not(.rd-tabs--fill) .rd-tabs__tab')];
    const i = tabs.findIndex((t) => t.getAttribute('aria-current') === 'page');
    if (i < 0) return;
    const next = tabs[(i + dir + tabs.length) % tabs.length];
    if (next) activate(next);
  }

  document.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    if (typing(event.target) || document.querySelector('dialog[open]')) return;
    const key = event.key;
    if (pending === 'g') {
      pending = '';
      window.clearTimeout(timer);
      const target = byKeys(`g ${key}`);
      if (target) {
        event.preventDefault();
        activate(target);
      }
      return;
    }
    if (key === 'g') {
      pending = 'g';
      timer = window.setTimeout(() => { pending = ''; }, 1200);
      return;
    }
    if (key === '/') {
      const search = document.querySelector('main input[type="search"]:not([disabled])');
      if (search) {
        event.preventDefault();
        search.focus();
      }
      return;
    }
    if (key === '[' || key === ']') {
      cycleTabs(key === ']' ? 1 : -1);
      return;
    }
    if (key === '?') {
      const help = document.getElementById('shortcuts');
      if (help) {
        event.preventDefault();
        help.showModal();
      }
      return;
    }
    const target = byKeys(key);
    if (target) {
      event.preventDefault();
      activate(target);
    }
  });

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-js="shortcuts-open"]')) {
      const help = document.getElementById('shortcuts');
      if (help) help.showModal();
    }
  });
})();
