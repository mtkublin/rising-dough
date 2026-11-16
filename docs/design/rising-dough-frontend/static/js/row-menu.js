/*
 * Row action menus and other anchored popovers (native popover attribute).
 * ≥ 768 px: positioned under the trigger, right-aligned (CSSOM only; no inline style attributes in markup).
 * < 768 px: CSS turns the menu into a bottom action sheet; no positioning needed.
 * The browser exposes the expanded state of popovertarget buttons natively; we support ↑/↓/Home/End inside menus,
 * and opens any popover marked [data-open] on load (used by the static "open" state pages).
 */
(() => {
  const desktop = window.matchMedia('(min-width: 48rem)');

  function triggerFor(pop) {
    return document.querySelector(`[popovertarget="${CSS.escape(pop.id)}"]:not([popovertargetaction="hide"])`);
  }

  function place(pop) {
    const trigger = triggerFor(pop);
    if (!trigger || !desktop.matches) {
      pop.style.removeProperty('top');
      pop.style.removeProperty('left');
      return;
    }
    const r = trigger.getBoundingClientRect();
    const w = pop.offsetWidth;
    const h = pop.offsetHeight;
    let left = r.right - w;
    if (pop.classList.contains('rd-period-pick')) left = r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - w - 8));
    let top = r.bottom + 4;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 4);
    pop.style.top = `${top}px`;
    pop.style.left = `${left}px`;
  }

  function items(pop) {
    return [...pop.querySelectorAll('[role="menuitem"]:not([aria-disabled="true"])')].filter((el) => el.offsetParent !== null);
  }

  document.addEventListener('toggle', (event) => {
    const pop = event.target;
    if (!(pop instanceof HTMLElement) || !pop.hasAttribute('popover')) return;
    const trigger = triggerFor(pop);
    const open = event.newState === 'open';
    if (trigger) trigger.dataset.state = open ? 'open' : '';
    if (open) {
      place(pop);
      const first = items(pop)[0];
      if (first && pop.getAttribute('role') === 'menu') first.focus({ preventScroll: true });
    } else if (trigger && pop.contains(document.activeElement)) {
      trigger.focus();
    }
  }, true);

  document.addEventListener('keydown', (event) => {
    const pop = event.target.closest && event.target.closest('[popover][role="menu"]');
    if (!pop) return;
    const list = items(pop);
    const i = list.indexOf(document.activeElement);
    let next = null;
    if (event.key === 'ArrowDown') next = list[(i + 1) % list.length];
    if (event.key === 'ArrowUp') next = list[(i - 1 + list.length) % list.length];
    if (event.key === 'Home') next = list[0];
    if (event.key === 'End') next = list[list.length - 1];
    if (next) {
      event.preventDefault();
      next.focus();
    }
  });

  // Choosing a menu item closes the menu (HTMX requests fire from the item itself).
  document.addEventListener('click', (event) => {
    const item = event.target.closest('[role="menuitem"]');
    if (!item || item.getAttribute('aria-disabled') === 'true') return;
    const pop = item.closest('[popover]');
    if (pop && pop.matches(':popover-open')) pop.hidePopover();
  });

  window.addEventListener('resize', () => {
    document.querySelectorAll('[popover]').forEach((pop) => {
      if (pop.matches(':popover-open')) place(pop);
    });
  });

  function init(root = document) {
    root.querySelectorAll('[popover][data-open]:not([data-ready])').forEach((pop) => {
      pop.dataset.ready = '';
      if (typeof pop.showPopover === 'function') pop.showPopover();
    });
  }

  init();
  document.addEventListener('htmx:load', (e) => init(e.target));
})();
