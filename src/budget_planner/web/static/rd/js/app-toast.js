/*
 * App glue for the toast and flash regions (T-UR02, ADR-0143); not part of the vendored handoff.
 *  1. HX-Trigger "toast" (web/htmx.py toast_payload): build the toast in #toast-root.
 *  2. Error responses (404/409/500...) carry only the OOB flash partial (web/errors.py): copy its
 *     content into the matching live region, keeping the region element (id, role, class).
 * Auto-dismiss comes from the vendored toast.js (window.RD.toast.arm), which loads before this module.
 */
(() => {
  function build(detail) {
    const toast = document.createElement('div');
    toast.className = 'rd-toast';
    toast.setAttribute('role', 'status');
    toast.dataset.js = 'toast';
    if (detail.variant) toast.dataset.variant = detail.variant;
    const text = document.createElement('span');
    text.textContent = detail.message || '';
    toast.append(text);
    if (detail.undo_url) {
      const form = document.createElement('form');
      form.method = 'post';
      form.action = detail.undo_url;
      const csrf = document.querySelector('meta[name="csrf-token"]');
      const fields = Object.assign({ _csrf_token: csrf ? csrf.content : '' }, detail.undo_payload || {});
      Object.keys(fields).forEach((key) => {
        const value = fields[key];
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = key;
        input.value = Array.isArray(value) ? value.join(',') : String(value);
        form.append(input);
      });
      const button = document.createElement('button');
      button.type = 'submit';
      button.className = 'rd-toast__action';
      button.textContent = 'undo';
      form.append(button);
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        const body = new FormData(form);
        fetch(detail.undo_url, {
          method: 'POST',
          body: new URLSearchParams(body),
          headers: { 'X-CSRF-Token': String(body.get('_csrf_token')), 'HX-Request': 'true' },
        }).then((response) => {
          toast.remove();
          if (response.ok) window.location.reload();
        });
      });
      toast.append(form);
    }
    return toast;
  }

  document.addEventListener('toast', (event) => {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const toast = build(event.detail || {});
    root.append(toast);
    if (window.RD && window.RD.toast) window.RD.toast.arm(toast);
  });

  /* HX-Trigger "dialog-close" (web/htmx.py Event.DIALOG_CLOSE): a 204 response leaves the confirm dialog
     open, so the server asks the page to close the dialog in #modal-root. */
  document.addEventListener('dialog-close', () => {
    const open = document.querySelector('#modal-root dialog[open]');
    if (open) open.close('cancel');
  });

  const FLASH_OOB = /id="flash-region(-assertive)?"[^>]*hx-swap-oob/;
  /* Same copy as the old shell (static/js/app-init.js) for error bodies that carry no flash. */
  const STATUS_TEXT = {
    400: 'The request was not accepted. Check the form and try again.',
    401: 'Your session has expired. Reload the page and sign in again.',
    403: 'The request was refused. Reload the page and try again.',
    404: 'That item was not found. It may have been removed.',
    409: 'That item changed in the meantime. Reload and try again.',
    503: 'A required service is unavailable. Try again shortly.',
  };
  const FALLBACK_TEXT = 'Something went wrong on our side. Try again.';
  const FORM_RERENDER = [422, 429];

  /* Same markup as fragments/flash/error.html. */
  function flashBox(message) {
    const box = document.createElement('div');
    box.className = 'rd-flash rd-flash--error';
    box.setAttribute('role', 'alert');
    const text = document.createElement('span');
    text.textContent = '\u25b2 ' + message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'rd-btn rd-btn--icon rd-flash__close';
    close.setAttribute('aria-label', 'Dismiss');
    close.dataset.js = 'flash-close';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'rd-icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '/static/rd/icons/sprite.svg#icon-close');
    svg.append(use);
    close.append(svg);
    box.append(text, close);
    return box;
  }

  /* The shell tells the server which flash markup to send (web/errors.py). */
  document.addEventListener('htmx:configRequest', (event) => {
    if (event.detail && event.detail.headers) event.detail.headers['X-Shell'] = 'rd';
    dropClosedFlashes();
  });

  /* In-dialog flash regions of dialogs that are no longer open are dropped with the next request. */
  function dropClosedFlashes() {
    document.querySelectorAll('dialog:not([open]) [data-flash-in-dialog]').forEach((el) => el.remove());
  }

  /* A dialog that opens again (showModal() sets its `open` attribute) starts without the flash of
     its last session. showModal() fires no event, so one observer on the `open` attribute does it. */
  new MutationObserver((records) => {
    records.forEach((record) => {
      const dialog = record.target;
      if (dialog instanceof HTMLDialogElement && dialog.open) {
        dialog.querySelectorAll('[data-flash-in-dialog]').forEach((el) => el.remove());
      }
    });
  }).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ['open'] });

  /* A modal <dialog> sits in the top layer, above #flash-region. While one is open the flash is
     shown in a live region inside the dialog instead (same role and aria-live as the page region),
     created empty first so assistive tech announces the content added next. Dialogs fetched into
     #modal-root are replaced on the next open; others drop it on the next request. */
  function show(id, nodes) {
    dropClosedFlashes();
    const open = document.querySelectorAll('dialog[open]');
    const dialog = open.length ? open[open.length - 1] : null;
    const page = document.getElementById(id);
    if (!dialog) {
      if (page) page.replaceChildren(...nodes);
      return;
    }
    let region = dialog.querySelector('[data-flash-in-dialog="' + id + '"]');
    if (region) {
      region.replaceChildren(...nodes);
      return;
    }
    region = document.createElement('div');
    region.className = 'rd-flash-region';
    region.dataset.flashInDialog = id;
    region.dataset.testid = 'flash-in-dialog';
    region.setAttribute('role', id === 'flash-region-assertive' ? 'alert' : 'status');
    region.setAttribute('aria-live', id === 'flash-region-assertive' ? 'assertive' : 'polite');
    dialog.prepend(region);
    setTimeout(() => region.replaceChildren(...nodes), 0);
  }

  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail || {};
    const xhr = detail.xhr;
    if (!xhr || xhr.status < 400) return;
    const body = xhr.responseText || '';
    if (FLASH_OOB.test(body)) {
      const incoming = new DOMParser().parseFromString(body, 'text/html');
      ['flash-region', 'flash-region-assertive'].forEach((id) => {
        const from = incoming.getElementById(id);
        const region = document.getElementById(id);
        if (from && region) show(id, Array.from(from.childNodes));
      });
    } else if (!FORM_RERENDER.includes(xhr.status)) {
      const region = document.getElementById('flash-region-assertive');
      if (region) show('flash-region-assertive', [flashBox(STATUS_TEXT[xhr.status] || FALLBACK_TEXT)]);
    } else {
      return;
    }
    detail.shouldSwap = false;
    detail.isError = false;
  });
})();
