/* Ledger filter bar: on phone the extra filters collapse behind the "filters" button.
 * Stand-in: a query string (?category=Takeaway, ?account=Checking) preselects the filters,
 * as the server would when Analytics or a blocked delete links into the ledger. */
(() => {
  const params = new URLSearchParams(window.location.search);
  document.querySelectorAll('[data-js="filters"] select[name]').forEach((select) => {
    const value = params.get(select.name);
    if (!value) return;
    let option = Array.from(select.options).find((o) => o.value === value);
    if (!option) {
      option = new Option(value, value);
      select.add(option);
    }
    select.value = value;
  });

  document.addEventListener('click', (event) => {
    const toggle = event.target.closest('[data-js="filters-toggle"]');
    if (!toggle) return;
    const form = toggle.closest('[data-js="filters"]');
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    toggle.setAttribute('aria-expanded', String(open));
    form.dataset.state = open ? 'expanded' : 'collapsed';
  });
})();
