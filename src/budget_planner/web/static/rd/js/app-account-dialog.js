/*
 * App glue for the new-account dialog (T-UR00b F4b); not part of the vendored handoff.
 * The hero currency chip follows the currency code typed in the field: a known ISO code (the
 * dialog's datalist) shows as typed, anything else keeps the base currency the dialog opened with.
 */
(() => {
  document.addEventListener('input', (event) => {
    const input = event.target;
    if (!input.matches || !input.matches('#new-account input[name="currency"]')) return;
    const form = input.closest('form');
    const chip = form && form.querySelector('.rd-dialog__cur');
    if (!chip) return;
    if (!chip.dataset.base) chip.dataset.base = chip.textContent;
    const code = input.value.trim().toUpperCase();
    const known = Array.from(form.querySelectorAll('#iso-codes option')).some((o) => o.value === code);
    chip.textContent = known ? code : chip.dataset.base;
  });
})();
