/*
 * Offline save failure (T-UR25, ADR-0134 section 4). No service worker.
 * An HTMX request that gets no response (htmx:sendError, htmx:timeout) swaps nothing, so an open
 * dialog keeps its typed input. This module shows the handoff's offline state at the top of the
 * form (or in #flash-region when the request came from outside a form), moves focus to it, and
 * removes it once a request succeeds. "retry now" re-submits the same form or re-issues the click.
 * The markup is cloned from <template id="rd-offline-template"> in layouts/base.html.
 */
(() => {
  const STATE = '[data-js="offline-state"]';
  const retryTargets = new WeakMap();

  function hostFor(elt) {
    const form = elt.closest('form');
    if (form) return { host: form, before: true };
    return { host: document.getElementById('flash-region'), before: false };
  }

  function show(elt) {
    const template = document.getElementById('rd-offline-template');
    if (!template || !(elt instanceof Element)) return;
    const { host, before } = hostFor(elt);
    if (!host) return;
    host.querySelectorAll(STATE).forEach((node) => node.remove());
    const state = template.content.firstElementChild.cloneNode(true);
    retryTargets.set(state, elt);
    if (before) host.prepend(state);
    else host.append(state);
    state.focus();
  }

  function clear(elt) {
    if (!(elt instanceof Element)) return;
    const { host } = hostFor(elt);
    if (host) host.querySelectorAll(STATE).forEach((node) => node.remove());
  }

  document.addEventListener('htmx:sendError', (event) => show(event.detail.elt || event.target));
  document.addEventListener('htmx:timeout', (event) => show(event.detail.elt || event.target));
  document.addEventListener('htmx:afterRequest', (event) => {
    if (event.detail.successful) clear(event.detail.elt || event.target);
  });

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-js="offline-retry"]');
    if (!button) return;
    const elt = retryTargets.get(button.closest(STATE));
    if (!elt || !elt.isConnected) return;
    if (elt instanceof HTMLFormElement) elt.requestSubmit();
    else if (elt instanceof HTMLElement && elt.matches('button[type="submit"], input[type="submit"]') && elt.form) elt.form.requestSubmit();
    else window.htmx.trigger(elt, 'click');
  });
})();
