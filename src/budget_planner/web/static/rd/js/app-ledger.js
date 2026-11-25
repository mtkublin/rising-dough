/*
 * Ledger page (T-UR09): a saved entry announces `ledger-stale` (HX-Trigger). The page refetches its
 * table region itself; the dialog that sent the save sits in #modal-root and answers with no body
 * (HX-Reswap none), so it is closed here. Errors answer 422 without the event and keep the dialog open.
 */
(() => {
  document.addEventListener('ledger-stale', () => {
    const open = document.querySelector('#modal-root dialog[open]');
    if (open) open.close('cancel');
  });

  /*
   * Back and Forward: htmx restores the page from an innerHTML snapshot, which keeps the markup but not
   * what the user typed or chose, so the filter fields would not match the restored URL and table (and
   * the next change would drop the hidden filter). The URL is the source of truth (the server pushes the
   * canonical /ledger?... URL on each filter change), so the fields are set back from it. Re-fetching on
   * every restore (hx-history="false") would cost a request per Back and flash the page; this does not.
   */
  document.addEventListener('htmx:historyRestore', () => {
    const form = document.getElementById('ledger-filters');
    if (!form) return;
    const params = new URLSearchParams(window.location.search);
    form.querySelectorAll('select[name], input[name]').forEach((field) => {
      if (field.name === 'view' || field.type === 'hidden') return;
      field.value = params.get(field.name) || '';
    });
  });
})();
