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

  const FLASH_OOB = /id="flash-region(-assertive)?"[^>]*hx-swap-oob/;
  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail || {};
    const xhr = detail.xhr;
    if (!xhr || xhr.status < 400 || !FLASH_OOB.test(xhr.responseText || '')) return;
    const incoming = new DOMParser().parseFromString(xhr.responseText, 'text/html');
    ['flash-region', 'flash-region-assertive'].forEach((id) => {
      const from = incoming.getElementById(id);
      const region = document.getElementById(id);
      if (from && region) region.replaceChildren(...from.childNodes);
    });
    detail.shouldSwap = false;
    detail.isError = false;
  });
})();
