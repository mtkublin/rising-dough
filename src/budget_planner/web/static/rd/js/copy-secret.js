/*
 * Copy button of a one-time secret (T-UR00b, handoff overlays/one-time-password).
 *   <div class="rd-secret"><output>...</output><button data-js="copy-secret">copy</button></div>
 * Copies the output's text to the clipboard and says so on the button for a moment.
 * Delegated, so a dialog swapped into #modal-root by HTMX is covered. No inline script (CSP).
 */
(() => {
  const DONE_MS = 2000;

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest('[data-js="copy-secret"]');
    if (!button) return;
    const output = button.closest('.rd-secret')?.querySelector('output');
    if (!output || !navigator.clipboard) return;
    const label = button.textContent;
    navigator.clipboard.writeText(output.textContent.trim()).then(() => {
      button.textContent = 'copied';
      setTimeout(() => {
        button.textContent = label;
      }, DONE_MS);
    });
  });
})();
