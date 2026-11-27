/*
 * Plan, year tab (T-UR00b, handoff overlay override--year-cell): a plain click on a month cell
 * turns it into the inline editor (the handoff's `rd-year-editor` form, cloned from the page's
 * <template data-js="year-cell-form">). A scope chip row in its own table row under the edited row
 * (so no cell value is covered; the radios stay in the form through their form attribute) offers
 * the template's chips (the server prints this month only and every month (default); the "every
 * <month>" text is filled from data-recurring-label) and starts on the cell's own tier (data-scope). Enter saves the
 * amount with the chosen scope (the form posts to the override route the dialog uses, through
 * HTMX) and focus returns to the cell once the grid reloads; a failed save answers 422 with the
 * override dialog in #modal-root, so the error is visible there. Escape cancels and gives the cell
 * back its focus. A modified click (Ctrl, Meta, Shift, Alt) or any other button keeps the link: it
 * opens the override dialog. Tab order: the chip row sits in a later table row, so Tab from the
 * amount jumps to the checked chip (the radio group is one tab stop), Tab from the chips goes to
 * the editor's save button and on to the rest of the row, and Shift+Tab walks back. No amount arithmetic here: the server formats and parses the amounts.
 */
(() => {
  let pending = null;

  function keyOf(cell) {
    return `${cell.dataset.action}|${cell.dataset.month}`;
  }

  function dropScopeRows() {
    document.querySelectorAll('[data-js="year-cell-scope-row"]').forEach((row) => row.remove());
  }

  function close(form) {
    dropScopeRows();
    const cell = form.previousElementSibling;
    form.remove();
    if (cell && cell.matches('[data-js="year-cell"]')) {
      cell.hidden = false;
      cell.focus();
    }
  }

  function closeOthers() {
    dropScopeRows();
    document.querySelectorAll('[data-js="year-cell-editor"]').forEach((form) => {
      const cell = form.previousElementSibling;
      form.remove();
      if (cell) cell.hidden = false;
    });
  }

  function open(cell) {
    const template = document.querySelector('template[data-js="year-cell-form"]');
    if (!template) return false;
    closeOthers();
    const form = template.content.firstElementChild.cloneNode(true);
    const input = form.querySelector('input[name="amount"]');
    const label = form.querySelector('[data-js="year-cell-label"]');
    const id = `ycell-${cell.dataset.month}-${cell.closest('tr').rowIndex}`;
    input.id = id;
    input.value = cell.dataset.amount || '';
    label.htmlFor = id;
    label.textContent = cell.dataset.editorLabel || '';
    form.action = cell.dataset.action;
    form.setAttribute('hx-post', cell.dataset.action);
    form.querySelector('input[name="year"]').value = cell.dataset.year;
    form.querySelector('input[name="month"]').value = cell.dataset.month;
    form.querySelector('[data-js="year-cell-recurring"]').textContent =
      cell.dataset.recurringLabel || '';
    form.querySelectorAll('input[name="tier"]').forEach((radio) => {
      radio.checked = radio.value === cell.dataset.scope;
    });
    pending = null;
    form.id = `${id}-form`;
    const scope = form.querySelector('.rd-year-editor__scope');
    const row = cell.closest('tr');
    const scopeRow = document.createElement('tr');
    scopeRow.className = 'rd-year__scope-row';
    scopeRow.dataset.js = 'year-cell-scope-row';
    const scopeCell = document.createElement('td');
    scopeCell.colSpan = row.cells.length;
    scope.querySelectorAll('input[name="tier"]').forEach((radio) => {
      radio.setAttribute('form', form.id);
    });
    scopeCell.append(scope);
    scopeRow.append(scopeCell);
    cell.hidden = true;
    cell.after(form);
    row.after(scopeRow);
    if (window.htmx) window.htmx.process(form);
    input.focus();
    return true;
  }

  document.addEventListener(
    'click',
    (event) => {
      const cell = event.target.closest && event.target.closest('[data-js="year-cell"]');
      if (!cell || event.button !== 0) return;
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      if (open(cell)) {
        event.preventDefault();
        event.stopPropagation();
      }
    },
    true,
  );

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!form.matches || !form.matches('[data-js="year-cell-editor"]')) return;
    const cell = form.previousElementSibling;
    pending = cell ? keyOf(cell) : null;
  });

  document.addEventListener('htmx:afterSettle', (event) => {
    if (!pending || !event.target || event.target.id !== 'main') return;
    const cell = [...document.querySelectorAll('[data-js="year-cell"]')].find(
      (c) => keyOf(c) === pending,
    );
    pending = null;
    if (cell) cell.focus();
  });

  function checkedChip() {
    const group = document.querySelector('[data-js="year-cell-scope-row"] [role="radiogroup"]');
    if (!group) return null;
    return group.querySelector('input[name="tier"]:checked') || group.querySelector('input[name="tier"]');
  }

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab' || event.ctrlKey || event.metaKey || event.altKey) return;
    const form = document.querySelector('[data-js="year-cell-editor"]');
    if (!form) return;
    const target = event.target;
    const chip = checkedChip();
    const save = form.querySelector('button[type="submit"]');
    let next = null;
    if (target.matches('input[name="amount"]') && form.contains(target) && !event.shiftKey) {
      next = chip;
    } else if (target.matches('input[name="tier"]') && target.getAttribute('form') === form.id) {
      next = event.shiftKey ? form.querySelector('input[name="amount"]') : save;
    } else if (target === save && event.shiftKey) {
      next = chip;
    }
    if (!next) return;
    event.preventDefault();
    next.focus();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const inside =
      event.target.closest &&
      event.target.closest('[data-js="year-cell-editor"], [data-js="year-cell-scope-row"]');
    const form = inside && document.querySelector('[data-js="year-cell-editor"]');
    if (!form) return;
    event.preventDefault();
    event.stopPropagation();
    pending = null;
    close(form);
  });
})();
