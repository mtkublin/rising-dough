/*
 * Toasts in #toast-root disappear after 8 s (pausing while hovered or focused); flash messages can be dismissed.
 * Works for toasts swapped in later by HTMX (htmx:load).
 */
(() => {
  const LIFETIME = 8000;

  function arm(toast) {
    if (toast.dataset.ready !== undefined) return;
    toast.dataset.ready = '';
    let remaining = LIFETIME;
    let started = Date.now();
    let timer = window.setTimeout(dismiss, remaining);
    function dismiss() {
      toast.dataset.state = 'leaving';
      window.setTimeout(() => toast.remove(), 250);
    }
    function pause() {
      window.clearTimeout(timer);
      remaining -= Date.now() - started;
    }
    function resume() {
      started = Date.now();
      timer = window.setTimeout(dismiss, Math.max(remaining, 1500));
    }
    toast.addEventListener('mouseenter', pause);
    toast.addEventListener('mouseleave', resume);
    toast.addEventListener('focusin', pause);
    toast.addEventListener('focusout', resume);
  }

  function init(root = document) {
    root.querySelectorAll('[data-js="toast"]').forEach(arm);
  }

  document.addEventListener('click', (event) => {
    const close = event.target.closest('[data-js="flash-close"]');
    if (close) close.closest('.rd-flash').remove();
  });

  /* HX-Trigger "toast" (web/htmx.py toast_payload, ADR-0143): build the toast from the payload. */
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
        const token = body.get('_csrf_token');
        fetch(detail.undo_url, {
          method: 'POST',
          body: new URLSearchParams(body),
          headers: { 'X-CSRF-Token': String(token), 'HX-Request': 'true' },
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
    arm(toast);
  });

  /* Error responses (404/409/500...) carry only the OOB flash partial (web/errors.py): swap that
     into the flash regions and leave the request target alone. */
  const FLASH_OOB = /id="flash-region(-assertive)?"[^>]*hx-swap-oob/;
  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail || {};
    const xhr = detail.xhr;
    if (!xhr || xhr.status < 400 || !FLASH_OOB.test(xhr.responseText || '')) return;
    detail.shouldSwap = true;
    detail.isError = false;
    detail.swapOverride = 'none';
  });

  window.RD = window.RD || {};
  window.RD.toast = { init, arm };
  init();
  document.addEventListener('htmx:load', (e) => init(e.target));
})();
