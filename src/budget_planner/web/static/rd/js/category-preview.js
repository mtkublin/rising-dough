/*
 * Category dialog preview chip (T-UR00b, handoff overlays/new-category--filled).
 * The chip under PREVIEW shows the typed name (`name` while empty) in the picked colour:
 *   <div class="rd-preview"> ... <span class="rd-chip" data-color="sky">Pets</span></div>
 * Delegated listeners on the document, so a dialog swapped into #modal-root by HTMX is covered.
 */
(() => {
  const EMPTY_NAME = 'name';

  function chipOf(form) {
    return form.querySelector('.rd-preview .rd-chip');
  }

  document.addEventListener('input', (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.name !== 'name') return;
    const form = input.closest('form');
    const chip = form && chipOf(form);
    if (chip) chip.textContent = input.value.trim() || EMPTY_NAME;
  });

  document.addEventListener('change', (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.name !== 'color') return;
    const form = input.closest('form');
    const chip = form && chipOf(form);
    if (!chip) return;
    const swatch = input.closest('.rd-swatch');
    const name = swatch ? swatch.dataset.color : '';
    if (name) chip.dataset.color = name;
    else delete chip.dataset.color;
  });
})();
