/*
 * Dialogs: native <dialog data-js="modal">.
 * - Any modal present in #modal-root on load or after an HTMX swap is opened with showModal().
 * - [data-js="dialog-close"] closes the nearest dialog; Esc is native.
 * - Focus returns to the element that opened it (the last focused element before showModal()).
 * Survives HTMX swaps: delegated listeners on document + init(root) re-run on htmx:load.
 */
(() => {
  const returnFocus = new WeakMap();

  function open(dialog) {
    if (dialog.open) return;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    returnFocus.set(dialog, opener);
    dialog.showModal();
    const first = dialog.querySelector('[autofocus]')
      || dialog.querySelector('input:not([type="hidden"]):not([readonly]):not([type="radio"]):not([type="checkbox"]), select, textarea')
      || dialog.querySelector('button');
    if (first) first.focus({ preventScroll: true });
  }

  function init(root = document) {
    root.querySelectorAll('dialog[data-js~="modal"]:not([data-ready])').forEach((dialog) => {
      dialog.dataset.ready = '';
      if (dialog.closest('#modal-root, #drawer-root')) open(dialog);
      dialog.addEventListener('close', () => {
        const target = returnFocus.get(dialog);
        if (target && target.isConnected) target.focus();
      });
    });
  }

  document.addEventListener('click', (event) => {
    const closer = event.target.closest('[data-js="dialog-close"]');
    if (closer) {
      const dialog = closer.closest('dialog');
      if (dialog) {
        event.preventDefault();
        dialog.close('cancel');
      }
      return;
    }
    // Click on the backdrop (outside the dialog box) closes sheets and dialogs.
    const dialog = event.target;
    if (dialog instanceof HTMLDialogElement && dialog.open) {
      const r = dialog.getBoundingClientRect();
      const inside = event.clientX >= r.left && event.clientX <= r.right && event.clientY >= r.top && event.clientY <= r.bottom;
      if (!inside) dialog.close('cancel');
    }
  });

  window.RD = window.RD || {};
  window.RD.dialog = { init, open };
  init();
  document.addEventListener('htmx:load', (e) => init(e.target));
})();
