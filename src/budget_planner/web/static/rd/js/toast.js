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

  window.RD = window.RD || {};
  window.RD.toast = { init, arm };
  init();
  document.addEventListener('htmx:load', (e) => init(e.target));
})();
