/*
 * Dependent form sections.
 *   <div data-show-when="amount_mode=formula">…</div>
 *   <p data-show-when="counts_as=liability">…</p>
 *   <div data-show-when="kind=planned|repeats amount_mode=fixed">…</div>
 * The element is shown only while every condition holds (space = AND, | = OR) for the current value of the
 * named control in the same form (FormData, so radios, selects, hidden inputs and checkboxes all work).
 * While hidden, the form controls inside it are disabled, so they are neither validated nor submitted.
 * Survives HTMX swaps: delegated `change` listener + init(root) on htmx:load.
 */
(() => {
  function holds(form, spec) {
    const data = new FormData(form);
    return spec.trim().split(/\s+/).every((cond) => {
      const [name, values] = cond.split('=');
      const current = data.getAll(name).map(String);
      return values.split('|').some((v) => current.includes(v));
    });
  }

  function setEnabled(el, on) {
    const controls = el.matches('input, select, textarea, button, output') ? [el] : el.querySelectorAll('input, select, textarea, button');
    controls.forEach((c) => {
      if (on) {
        if (c.dataset.revealDisabled !== undefined) {
          c.disabled = false;
          delete c.dataset.revealDisabled;
        }
      } else if (!c.disabled) {
        c.disabled = true;
        c.dataset.revealDisabled = '';
      }
    });
  }

  function update(form) {
    // Enable everything first so FormData sees the controls that decide visibility.
    const parts = [...form.querySelectorAll('[data-show-when]')];
    parts.forEach((el) => setEnabled(el, true));
    parts.forEach((el) => {
      const on = holds(form, el.dataset.showWhen);
      el.hidden = !on;
      setEnabled(el, on);
    });
  }

  function init(root = document) {
    const forms = new Set();
    root.querySelectorAll('[data-show-when]').forEach((el) => { if (el.form || el.closest('form')) forms.add(el.form || el.closest('form')); });
    forms.forEach(update);
  }

  document.addEventListener('change', (event) => {
    const form = event.target.closest('form');
    if (form && form.querySelector('[data-show-when]')) update(form);
  });

  window.RD = window.RD || {};
  window.RD.reveal = { init, update };
  init();
  document.addEventListener('htmx:load', (e) => init(e.target));
})();
