/*
 * Copy button of a one-time secret (T-UR00b, handoff overlays/one-time-password).
 *   <div class="rd-secret"><output>...</output><button data-js="copy-secret">copy</button></div>
 * Copies the output's text to the clipboard and says so on the button for a moment. When the
 * clipboard is unavailable or refuses, the text is selected instead and the button reads
 * "copy failed" (never silent, no unhandled rejection). Delegated, so a dialog swapped into
 * #modal-root by HTMX is covered. No inline script (CSP).
 */
(() => {
  const DONE_MS = 2000;

  function flash(button, text) {
    const label = button.dataset.label || button.textContent;
    button.dataset.label = label;
    button.textContent = text;
    setTimeout(() => {
      button.textContent = label;
    }, DONE_MS);
  }

  function selectText(output) {
    const range = document.createRange();
    range.selectNodeContents(output);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
  }

  function failed(button, output) {
    selectText(output);
    flash(button, 'copy failed');
  }

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const button = target.closest('[data-js="copy-secret"]');
    if (!button) return;
    const output = button.closest('.rd-secret')?.querySelector('output');
    if (!output) return;
    if (!navigator.clipboard) {
      failed(button, output);
      return;
    }
    navigator.clipboard
      .writeText(output.textContent.trim())
      .then(() => flash(button, 'copied'))
      .catch(() => failed(button, output));
  });
})();
