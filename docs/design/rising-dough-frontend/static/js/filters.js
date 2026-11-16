/* Ledger filter bar: on phone the extra filters collapse behind the "filters" button. */
(() => {
  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-js="filters-toggle"]');
    if (!toggle) return;
    const form = toggle.closest('[data-js="filters"]');
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    form.dataset.state = open ? 'expanded' : 'collapsed';
  });
})();
