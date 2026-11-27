/*
 * Plan, year tab (T-UR00b, handoff overlay override--year-cell; T-UR77): a plain click on a month
 * cell turns it into the inline editor (the handoff's `rd-year-editor` form, cloned from the
 * page's <template data-js="year-cell-form">). Two scope chips hover right beneath the edited cell
 * as a fixed-position popover (no outer box, rows below do not shift): "this month only", always
 * preselected, and "every <month>" (text from data-recurring-label, which the server takes from
 * tier_labels). The year cell never writes the default tier. The popover is placed from the cell's
 * rectangle and clamped into the viewport at both edges, and follows the cell when the grid or the
 * page scrolls. Enter saves the amount with the chosen scope (the form posts to the override route
 * the dialog uses, through HTMX) and focus returns to the cell once the grid reloads; a failed
 * save answers 422 with the override dialog in #modal-root, so the error is visible there. Escape
 * cancels and gives the cell back its focus. A modified click (Ctrl, Meta, Shift, Alt) or any other
 * button keeps the link: it opens the override dialog. Tab order is the form's own: the amount,
 * then the checked chip (the radio group is one tab stop), then the save button. No amount
 * arithmetic here: the server formats and parses the amounts.
 */
(() => {
  const MARGIN = 8;
  const GAP = 0;
  let pending = null;
  const SETTLE_MS = [120, 350, 700];
  let placed = null;
  let stop = null;

  function keyOf(cell) {
    return `${cell.dataset.action}|${cell.dataset.month}`;
  }

  // Under the edited cell (above it when there is no room below), starting at its left edge,
  // clamped into the viewport.
  function place(form) {
    const group = form.querySelector('.rd-year-editor__scope');
    if (!group) return;
    const box = form.getBoundingClientRect();
    const room = document.documentElement.clientWidth - 2 * MARGIN;
    group.style.setProperty('max-width', `${room}px`);
    const width = Math.min(group.offsetWidth, room);
    const left = Math.max(MARGIN, Math.min(box.left, MARGIN + room - width));
    // The group's own top margin shifts it down from `top`, so it counts in both placements.
    const lift = parseFloat(getComputedStyle(group).marginTop) || 0;
    const height = group.offsetHeight + lift;
    // The visible area is the visual viewport: the on-screen keyboard or a pinch shrinks and moves
    // it inside the layout viewport the fixed group is laid out against (T-UR92).
    const vv = window.visualViewport;
    const seenTop = vv ? vv.offsetTop : 0;
    const seenBottom = vv ? vv.offsetTop + vv.height : document.documentElement.clientHeight;
    const fitsBelow = box.bottom + GAP + height <= seenBottom;
    const above = box.top - GAP - height;
    const top = !fitsBelow && above >= seenTop ? above : box.bottom;
    group.style.setProperty('top', `${top}px`);
    group.style.setProperty('left', `${left}px`);
  }

  // Every source that moves the cell or the visible area re-places the group, once per frame:
  // window and grid scroll (captured, scroll does not bubble), resize, visualViewport resize and
  // scroll (keyboard, pinch: no window event), and a short settle after the editor opens while
  // the keyboard animates in (T-UR92, R26).
  function track(form) {
    untrack();
    let frame = 0;
    const run = () => {
      frame = 0;
      place(form);
    };
    placed = () => {
      if (!frame) frame = window.requestAnimationFrame(run);
    };
    const vv = window.visualViewport;
    window.addEventListener('resize', placed);
    window.addEventListener('scroll', placed, true);
    if (vv) {
      vv.addEventListener('resize', placed);
      vv.addEventListener('scroll', placed);
    }
    const settle = SETTLE_MS.map((ms) => window.setTimeout(placed, ms));
    stop = () => {
      window.removeEventListener('resize', placed);
      window.removeEventListener('scroll', placed, true);
      if (vv) {
        vv.removeEventListener('resize', placed);
        vv.removeEventListener('scroll', placed);
      }
      settle.forEach((id) => window.clearTimeout(id));
      if (frame) window.cancelAnimationFrame(frame);
    };
  }

  function untrack() {
    if (!stop) return;
    stop();
    stop = null;
    placed = null;
  }

  function close(form) {
    untrack();
    const cell = form.previousElementSibling;
    form.remove();
    if (cell && cell.matches('[data-js="year-cell"]')) {
      cell.hidden = false;
      cell.focus();
    }
  }

  function closeOthers() {
    untrack();
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
      radio.checked = radio.value === 'one-off';
    });
    pending = null;
    cell.hidden = true;
    cell.after(form);
    if (window.htmx) window.htmx.process(form);
    place(form);
    track(form);
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
    untrack();
    const cell = [...document.querySelectorAll('[data-js="year-cell"]')].find(
      (c) => keyOf(c) === pending,
    );
    pending = null;
    if (cell) cell.focus();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const inside = event.target.closest && event.target.closest('[data-js="year-cell-editor"]');
    const form = inside && document.querySelector('[data-js="year-cell-editor"]');
    if (!form) return;
    event.preventDefault();
    event.stopPropagation();
    pending = null;
    close(form);
  });
})();
