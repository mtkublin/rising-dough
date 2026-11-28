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

  // A request from a form shows the inline state at the top of that form; any other request
  // shows the handoff's full offline card in <main> (the page content hides meanwhile).
  function hostFor(elt) {
    const form = elt.closest('form');
    if (form) return { host: form, page: false };
    return { host: document.getElementById('main'), page: true };
  }

  function remove(host, page) {
    host.querySelectorAll(STATE).forEach((node) => node.remove());
    if (!page) return;
    host.querySelectorAll('[data-offline-hidden]').forEach((node) => {
      node.hidden = false;
      node.removeAttribute('data-offline-hidden');
    });
    document.querySelectorAll('[data-offline-current]').forEach((node) => {
      node.setAttribute('aria-current', 'page');
      node.removeAttribute('data-offline-current');
    });
  }

  function show(elt) {
    if (!(elt instanceof Element)) return;
    const { host, page } = hostFor(elt);
    const template = document.getElementById(
      page ? 'rd-offline-page-template' : 'rd-offline-template',
    );
    if (!template || !host) return;
    remove(host, page);
    if (page) {
      Array.from(host.children).forEach((node) => {
        node.hidden = true;
        node.setAttribute('data-offline-hidden', '');
      });
      /* The card is a page of its own (like the handoff's): no nav item is the current one. */
      document.querySelectorAll('[aria-current="page"]').forEach((node) => {
        node.removeAttribute('aria-current');
        node.setAttribute('data-offline-current', '');
      });
    }
    const state = template.content.firstElementChild.cloneNode(true);
    const title = state.querySelector('[data-js="offline-title"]');
    if (page && title) {
      const heading = document.createElement('h1');
      heading.className = title.className;
      heading.id = title.id;
      heading.textContent = title.textContent;
      title.replaceWith(heading);
    }
    retryTargets.set(state, elt);
    host.prepend(state);
    state.focus();
  }

  function clear(elt) {
    if (!(elt instanceof Element)) return;
    const { host, page } = hostFor(elt);
    if (host) remove(host, page);
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
