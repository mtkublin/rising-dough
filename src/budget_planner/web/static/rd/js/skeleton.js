/*
 * Skeleton while a list request runs (handoff states/loading, T-UR00b). A control with
 * data-skeleton="<selector>" swaps the children of that region for the skeleton of
 * <template id="rd-skeleton-template"> when its request starts and marks the nearest
 * [data-skeleton-busy] ancestor aria-busy. The response replaces the region (the controls use
 * outerHTML); a request that fails puts the previous list back.
 */
(() => {
  const saved = new WeakMap();

  function region(elt) {
    const selector = elt instanceof Element ? elt.getAttribute('data-skeleton') : null;
    return selector ? document.querySelector(selector) : null;
  }

  document.addEventListener('htmx:beforeRequest', (event) => {
    const elt = event.detail.elt;
    const target = region(elt);
    const template = document.getElementById('rd-skeleton-template');
    if (!target || !template) return;
    saved.set(elt, Array.from(target.childNodes));
    target.replaceChildren(template.content.cloneNode(true));
    const busy = target.closest('[data-skeleton-busy]');
    if (busy) busy.setAttribute('aria-busy', 'true');
  });

  function restore(event) {
    const elt = event.detail.elt;
    const target = region(elt);
    const nodes = saved.get(elt);
    if (!target || !nodes) return;
    saved.delete(elt);
    if (!target.isConnected) return;
    target.replaceChildren(...nodes);
    const busy = target.closest('[data-skeleton-busy]');
    if (busy) busy.removeAttribute('aria-busy');
  }

  ['htmx:sendError', 'htmx:responseError', 'htmx:timeout', 'htmx:sendAbort'].forEach((name) =>
    document.addEventListener(name, restore)
  );
})();
