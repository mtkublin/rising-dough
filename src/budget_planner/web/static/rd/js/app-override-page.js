/*
 * App glue for the override dialog opened as a plain page (T-UR84); not part of the vendored handoff.
 * Opens the dialog rendered in the page body as a modal once scripts run.
 */
(() => {
  const open = () => {
    const dialog = document.querySelector('.rd-override-page dialog');
    if (dialog && window.RD && window.RD.dialog) window.RD.dialog.open(dialog);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', open);
  else open();
})();
