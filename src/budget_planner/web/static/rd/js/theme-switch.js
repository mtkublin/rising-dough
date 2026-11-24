/*
 * Settings › Preferences › theme: system · light · dark. Saved per browser (localStorage "rd-theme").
 * theme.js applies the saved value before first paint on every page.
 */
(() => {
  const KEY = 'rd-theme';

  function current() {
    try {
      return window.localStorage.getItem(KEY) || 'system';
    } catch {
      return 'system';
    }
  }

  function apply(value) {
    if (value === 'light' || value === 'dark') document.documentElement.dataset.theme = value;
    else delete document.documentElement.dataset.theme;
    try {
      window.localStorage.setItem(KEY, value);
    } catch {
      /* storage unavailable: theme still applies for this page */
    }
  }

  function init(root = document) {
    root.querySelectorAll('[data-js="theme-switch"]').forEach((group) => {
      const value = current();
      group.querySelectorAll('[data-theme-value]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.themeValue === value)));
    });
  }

  document.addEventListener('click', (event) => {
    const option = event.target.closest('[data-js="theme-switch"] [data-theme-value]');
    if (option) apply(option.dataset.themeValue);
  });

  init();
  document.addEventListener('htmx:load', (e) => init(e.target));
})();
