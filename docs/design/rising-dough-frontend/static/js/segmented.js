/*
 * Segmented controls built from <button aria-pressed>: pressing one un-presses its siblings.
 * (Radio-based segmented controls need no JS.) HTMX requests the new content from the pressed button.
 */
(() => {
  document.addEventListener('click', (event) => {
    const option = event.target.closest('.rd-segmented > button.rd-segmented__option');
    if (!option) return;
    option.parentElement.querySelectorAll(':scope > button.rd-segmented__option').forEach((b) => {
      b.setAttribute('aria-pressed', String(b === option));
    });
  });
})();
