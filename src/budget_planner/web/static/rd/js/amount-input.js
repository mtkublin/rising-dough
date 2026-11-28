/*
 * Amount input: decimal keypad (inputmode="decimal" in markup), right-aligned (CSS),
 * accepts digits, one decimal separator and thousands commas. Selects the value on focus.
 * It never formats or computes: the server returns the formatted value.
 */
(() => {
  document.addEventListener('focusin', (event) => {
    const input = event.target;
    if (input.matches && input.matches('[data-js="amount-input"]') && !input.readOnly) {
      /* select() also focuses the input (Chromium): when the user has moved on before the frame
         (tab, click, a fast fill), selecting would pull focus back and send the next field's text here. */
      window.requestAnimationFrame(() => {
        if (document.activeElement === input) input.select();
      });
    }
  });

  document.addEventListener('beforeinput', (event) => {
    const input = event.target;
    if (!input.matches || !input.matches('[data-js="amount-input"]')) return;
    if (event.inputType && event.inputType.startsWith('delete')) return;
    if (event.data && /[^\d.,\s]/.test(event.data)) event.preventDefault();
  });
})();
