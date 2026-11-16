/*
 * Bulk row selection on ledger tables ([data-js="bulk"]).
 * Checkbox column is hidden until something is selected (data-state="selecting" on the table).
 * Shift+click selects a range. The bar shows "<n> selected"; clear resets.
 */
(() => {
  let last = null;

  function boxes(table) {
    return [...table.querySelectorAll('[data-js="bulk-item"]')];
  }

  function update(table) {
    const form = table.closest('form');
    const all = boxes(table);
    const n = all.filter((b) => b.checked).length;
    table.dataset.state = n > 0 ? 'selecting' : '';
    if (!n) table.removeAttribute('data-state');
    const head = table.querySelector('[data-js="bulk-all"]');
    if (head) {
      head.checked = n > 0 && n === all.length;
      head.indeterminate = n > 0 && n < all.length;
    }
    const bar = form && form.querySelector('[data-js="bulk-bar"]');
    if (bar) {
      bar.hidden = n === 0;
      const count = bar.querySelector('[data-js="bulk-count"]');
      if (count) count.textContent = `${n} selected`;
    }
  }

  document.addEventListener('click', (event) => {
    const box = event.target.closest('[data-js="bulk-item"]');
    if (box) {
      const table = box.closest('[data-js="bulk"]');
      if (event.shiftKey && last && last !== box) {
        const all = boxes(table);
        const [a, b] = [all.indexOf(last), all.indexOf(box)].sort((x, y) => x - y);
        all.slice(a, b + 1).forEach((el) => { el.checked = box.checked; });
      }
      last = box;
      update(table);
      return;
    }
    const allBox = event.target.closest('[data-js="bulk-all"]');
    if (allBox) {
      const table = allBox.closest('[data-js="bulk"]');
      boxes(table).forEach((b) => { b.checked = allBox.checked; });
      update(table);
      return;
    }
    const clear = event.target.closest('[data-js="bulk-clear"]');
    if (clear) {
      const form = clear.closest('form');
      const table = form.querySelector('[data-js="bulk"]');
      boxes(table).forEach((b) => { b.checked = false; });
      update(table);
    }
  });

  // x toggles the focused row's checkbox (keyboard path into selection mode)
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'x' || event.target.closest('input, textarea, select')) return;
    const row = event.target.closest('[data-js="bulk"] tr');
    const box = row && row.querySelector('[data-js="bulk-item"]');
    if (box) {
      event.preventDefault();
      box.click();
    }
  });
})();
