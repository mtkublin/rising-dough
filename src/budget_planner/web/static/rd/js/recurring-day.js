/*
 * App glue for the repeats tab and the edit-recurring dialog (T-UR79, R19); not part of the vendored handoff.
 * The day-of-month field follows the start date (2026-12-06 -> 6) until the user types in it; a value the
 * server rendered (edit, 422) counts as typed. Server validation is unchanged; without JS the field stays plain.
 */
(() => {
  const DAY = '#field-day_of_month';
  const START = '#field-start_date';

  const dayOf = (iso) => {
    const m = /^\d{4}-\d{2}-(\d{2})$/.exec(iso || '');
    return m ? String(Number(m[1])) : '';
  };

  const follow = (form) => {
    const day = form && form.querySelector(DAY);
    const start = form && form.querySelector(START);
    if (!day || !start || day.dataset.typed === '1') return;
    const value = dayOf(start.value);
    if (value) day.value = value;
  };

  const arm = (root) => {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll(DAY).forEach((day) => {
      if (day.dataset.armed === '1') return;
      day.dataset.armed = '1';
      if (day.value !== '') day.dataset.typed = '1';
      else follow(day.closest('form'));
    });
  };

  document.addEventListener('input', (event) => {
    const el = event.target;
    if (!el.matches) return;
    if (el.matches(DAY)) el.dataset.typed = '1';
    else if (el.matches(START)) follow(el.closest('form'));
  });
  document.addEventListener('change', (event) => {
    const el = event.target;
    if (el.matches && el.matches(START)) follow(el.closest('form'));
  });
  document.addEventListener('htmx:load', (event) => arm(event.target));
  arm(document);
})();
