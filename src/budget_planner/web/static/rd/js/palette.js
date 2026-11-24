/*
 * Command palette: Ctrl K / ⌘ K opens #palette (a <dialog> present on every app page).
 * Type to filter the commands already in the DOM, ↑/↓ to move, Enter to run (follows data-href).
 * The query is echoed into the empty state with textContent (never innerHTML).
 */
(() => {
  function options(dialog) {
    return [...dialog.querySelectorAll('[role="option"]')];
  }

  function visible(dialog) {
    return options(dialog).filter((o) => !o.hidden);
  }

  function select(dialog, option) {
    const input = dialog.querySelector('[data-js="palette-input"]');
    options(dialog).forEach((o) => o.setAttribute('aria-selected', String(o === option)));
    if (option) {
      input.setAttribute('aria-activedescendant', option.id);
      option.scrollIntoView({ block: 'nearest' });
    } else {
      input.removeAttribute('aria-activedescendant');
    }
  }

  function filter(dialog) {
    const input = dialog.querySelector('[data-js="palette-input"]');
    const q = input.value.trim().toLowerCase();
    options(dialog).forEach((o) => {
      o.hidden = q !== '' && !o.textContent.toLowerCase().includes(q);
    });
    dialog.querySelectorAll('.rd-palette__list > li').forEach((group) => {
      group.hidden = !group.querySelector('[role="option"]:not([hidden])');
    });
    const empty = dialog.querySelector('[data-js="palette-empty"]');
    const any = visible(dialog).length > 0;
    if (empty) {
      empty.hidden = any;
      const echo = empty.querySelector('[data-js="palette-query"]');
      if (echo) echo.textContent = input.value;
    }
    select(dialog, visible(dialog)[0] || null);
  }

  function run(option) {
    const href = option && option.dataset.href;
    if (!href) return;
    if (href === '#shortcuts') {
      option.closest('dialog').close();
      const help = document.getElementById('shortcuts');
      if (help) help.showModal();
      return;
    }
    window.location.assign(href);
  }

  function openPalette() {
    const dialog = document.getElementById('palette');
    if (!dialog || dialog.open) return;
    const input = dialog.querySelector('[data-js="palette-input"]');
    input.value = '';
    filter(dialog);
    dialog.showModal();
    input.focus();
  }

  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openPalette();
      return;
    }
    const dialog = event.target.closest && event.target.closest('[data-js~="palette"]');
    if (!dialog) return;
    const list = visible(dialog);
    const current = list.findIndex((o) => o.getAttribute('aria-selected') === 'true');
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      select(dialog, list[(current + step + list.length) % list.length] || null);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      run(list[current]);
    }
  });

  document.addEventListener('input', (event) => {
    if (event.target.matches('[data-js="palette-input"]')) filter(event.target.closest('dialog'));
  });

  document.addEventListener('click', (event) => {
    const option = event.target.closest('[data-js~="palette"] [role="option"]');
    if (option) run(option);
  });

  window.RD = window.RD || {};
  window.RD.openPalette = openPalette;
})();
