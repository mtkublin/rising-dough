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
})();
