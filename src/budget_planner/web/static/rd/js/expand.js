/* Disclosure buttons ([data-js="expand"]): toggle aria-expanded and the controlled element's hidden. */
(() => {
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-js="expand"]');
    if (!button) return;
    const target = document.getElementById(button.getAttribute('aria-controls'));
    const open = button.getAttribute('aria-expanded') !== 'true';
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'Hide formula and overrides' : 'Show formula and overrides');
    if (target) target.hidden = !open;
  });
})();
