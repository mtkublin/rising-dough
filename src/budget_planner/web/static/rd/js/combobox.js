/*
 * Category picker (combobox): 4 recent categories as radios + a search that opens the full list
 * already in the DOM under the field. Type to filter, ↑/↓ move, Enter picks, Esc closes.
 * Picking sets a hidden input name="category" (and unchecks the recent radios).
 */
(() => {
  function parts(field) {
    return {
      field,
      opener: field.querySelector('[data-js="combobox-open"]'),
      panel: field.querySelector('.rd-catpick'),
      input: field.querySelector('[data-js="combobox-input"]'),
      list: field.querySelector('[role="listbox"]'),
      empty: field.querySelector('[data-js="combobox-empty"]'),
    };
  }

  const visible = (p) => [...p.list.querySelectorAll('[role="option"]')].filter((o) => !o.hidden);

  function setActive(p, option) {
    p.list.querySelectorAll('[role="option"]').forEach((o) => o.setAttribute('aria-selected', String(o === option)));
    if (option) {
      p.input.setAttribute('aria-activedescendant', option.id);
      option.scrollIntoView({ block: 'nearest' });
    } else {
      p.input.removeAttribute('aria-activedescendant');
    }
  }

  function open(p) {
    p.panel.hidden = false;
    p.opener.setAttribute('aria-expanded', 'true');
    p.input.focus();
    filter(p);
  }

  function close(p, focusOpener = true) {
    p.panel.hidden = true;
    p.opener.setAttribute('aria-expanded', 'false');
    if (focusOpener) p.opener.focus();
  }

  function filter(p) {
    const q = p.input.value.trim().toLowerCase();
    p.list.querySelectorAll('[role="option"]').forEach((o) => {
      o.hidden = q !== '' && !o.textContent.toLowerCase().includes(q);
    });
    const any = visible(p).length > 0;
    p.list.hidden = !any;
    if (p.empty) {
      p.empty.hidden = any;
      p.empty.querySelectorAll('[data-js="combobox-query"]').forEach((el) => { el.textContent = p.input.value; });
    }
    setActive(p, visible(p)[0] || null);
  }

  function pick(p, option) {
    const value = option.dataset.value;
    p.field.querySelectorAll('input[type="radio"][name="category"]').forEach((r) => { r.checked = r.value === value; });
    let hidden = p.field.querySelector('input[type="hidden"][name="category"]');
    const matchedRecent = [...p.field.querySelectorAll('input[type="radio"][name="category"]')].some((r) => r.checked);
    if (!matchedRecent) {
      if (!hidden) {
        hidden = document.createElement('input');
        hidden.type = 'hidden';
        hidden.name = 'category';
        p.field.append(hidden);
      }
      hidden.value = value;
      p.opener.lastChild.textContent = option.textContent.replace(/[↓↑⇄±].*$/, '').trim();
    } else {
      if (hidden) hidden.remove();
      leadRow(p.field.querySelector('input[type="radio"][name="category"]:checked'));
    }
    // Let dependent fields (reveal.js) react, e.g. Transit shows the destination account.
    p.field.dispatchEvent(new Event('change', { bubbles: true }));
    close(p);
  }

  document.addEventListener('click', (event) => {
    const opener = event.target.closest('[data-js="combobox-open"]');
    if (opener) {
      const p = parts(opener.closest('[data-js="combobox"]'));
      if (p.panel.hidden) open(p); else close(p);
      return;
    }
    const option = event.target.closest('[data-js="combobox"] [role="option"]');
    if (option) pick(parts(option.closest('[data-js="combobox"]')), option);
  });

  /* The picked recent chip leads the row (the server renders it first on a re-render,
     categories.lead_with_selected; ADR-0151 amendment 2026-11-25). Nothing is dropped. */
  function leadRow(radio) {
    const label = radio && radio.closest('.rd-chip-option');
    const row = label && label.parentElement;
    if (!row || !row.classList.contains('rd-catfield__recent')) return;
    const first = row.querySelector('.rd-chip-option');
    if (!first || first === label) return;
    const focused = document.activeElement === radio;
    first.before(label);
    if (focused) radio.focus({ preventScroll: true });
  }

  /* Only a pointer pick leads. Arrow/Space on the group fire a click with detail 0: the row stays
     put, focus stays on the active radio and the group stays walkable. A click on the chip label
     reaches the radio as a synthetic click whose detail is 0 in WebKit, so the pointer press on the
     chip is remembered instead of trusting detail alone. */
  let pressedChip = null;
  document.addEventListener('pointerdown', (event) => {
    pressedChip = event.target.closest('.rd-catfield__recent .rd-chip-option');
  });
  document.addEventListener('keydown', () => { pressedChip = null; });
  document.addEventListener('click', (event) => {
    if (!event.target.matches('.rd-catfield__recent input[type="radio"]') || !event.target.checked) return;
    const byPointer = event.detail > 0 || pressedChip === event.target.closest('.rd-chip-option');
    pressedChip = null;
    if (byPointer) leadRow(event.target);
  });

  document.addEventListener('input', (event) => {
    if (event.target.matches('[data-js="combobox-input"]')) filter(parts(event.target.closest('[data-js="combobox"]')));
  });

  document.addEventListener('keydown', (event) => {
    if (!event.target.matches('[data-js="combobox-input"]')) return;
    const p = parts(event.target.closest('[data-js="combobox"]'));
    const list = visible(p);
    const i = list.findIndex((o) => o.getAttribute('aria-selected') === 'true');
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive(p, list[(i + step + list.length) % list.length] || null);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (list[i]) pick(p, list[i]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close(p);
    }
  });

  document.addEventListener('focusout', (event) => {
    const field = event.target.closest && event.target.closest('[data-js="combobox"]');
    if (!field) return;
    window.setTimeout(() => {
      const p = parts(field);
      if (!field.contains(document.activeElement) && !p.panel.hidden) close(p, false);
    }, 0);
  });
})();
