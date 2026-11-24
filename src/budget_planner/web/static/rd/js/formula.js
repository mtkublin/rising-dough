/*
 * Formula amount: components of sign · percentage · categories (multi-select).
 * + add component clones the last component (cleared); ✕ removes (hidden while only one remains).
 * Multi-select: the trigger toggles its checkbox list; chips in the trigger mirror the checked boxes.
 * Field names are re-indexed (components[0][…], components[1][…]) after add/remove.
 * The next amount is computed by the server (HTMX), never here.
 */
(() => {
  function components(formula) {
    return [...formula.querySelectorAll('[data-js="formula-component"]')];
  }

  function reindex(formula) {
    const list = components(formula);
    list.forEach((comp, i) => {
      comp.querySelectorAll('[name^="components["]').forEach((el) => {
        el.name = el.name.replace(/components\[\d+\]/, `components[${i}]`);
      });
      const legend = comp.querySelector('legend');
      if (legend) legend.textContent = `Component ${i + 1}`;
      const remove = comp.querySelector('[data-js="formula-remove"]');
      if (remove) {
        remove.hidden = list.length === 1;
        remove.setAttribute('aria-label', `Remove component ${i + 1}`);
      }
    });
  }

  function syncChips(comp) {
    const trigger = comp.querySelector('[data-js="multiselect"]');
    const holder = trigger.querySelector('.rd-msel__chips');
    holder.replaceChildren();
    const checked = [...comp.querySelectorAll('.rd-msel input[type="checkbox"]:checked')];
    if (checked.length === 0) {
      const ph = document.createElement('span');
      ph.className = 'rd-msel__placeholder';
      ph.textContent = 'pick categories';
      holder.append(ph);
      return;
    }
    checked.forEach((box) => {
      const chip = box.closest('.rd-msel__opt').querySelector('.rd-chip');
      if (chip) holder.append(chip.cloneNode(true));
    });
  }

  function toggleList(trigger, force) {
    const list = document.getElementById(trigger.getAttribute('aria-controls'));
    const open = force ?? list.hidden;
    list.hidden = !open;
    trigger.setAttribute('aria-expanded', String(open));
    if (open) {
      const filter = list.querySelector('[data-js="multiselect-filter"]');
      if (filter) filter.focus();
    }
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-js="multiselect"]');
    if (trigger) {
      toggleList(trigger);
      return;
    }
    const add = event.target.closest('[data-js="formula-add"]');
    if (add) {
      const formula = add.closest('[data-js="formula"]');
      const last = components(formula).pop();
      const copy = last.cloneNode(true);
      const uid = `c${Date.now().toString(36)}`;
      copy.querySelectorAll('[id]').forEach((el) => { el.id = `${el.id}-${uid}`; });
      copy.querySelectorAll('[aria-controls]').forEach((el) => el.setAttribute('aria-controls', `${el.getAttribute('aria-controls')}-${uid}`));
      copy.querySelectorAll('[aria-describedby]').forEach((el) => el.removeAttribute('aria-describedby'));
      copy.querySelectorAll('[aria-invalid]').forEach((el) => el.removeAttribute('aria-invalid'));
      copy.querySelectorAll('.rd-comp__err').forEach((el) => el.remove());
      copy.querySelectorAll('input[type="checkbox"]').forEach((el) => { el.checked = false; });
      copy.querySelectorAll('input[inputmode="decimal"]').forEach((el) => { el.value = ''; });
      const list = copy.querySelector('.rd-msel');
      if (list) list.hidden = true;
      copy.querySelector('[data-js="multiselect"]').setAttribute('aria-expanded', 'false');
      if (!copy.querySelector('[data-js="formula-remove"]')) {
        const spacer = copy.querySelector('.rd-comp__spacer');
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'rd-btn rd-btn--icon rd-comp__remove';
        remove.dataset.js = 'formula-remove';
        remove.textContent = '✕';
        if (spacer) spacer.replaceWith(remove);
      }
      last.after(copy);
      syncChips(copy);
      reindex(formula);
      copy.querySelector('input[inputmode="decimal"]').focus();
      return;
    }
    const remove = event.target.closest('[data-js="formula-remove"]');
    if (remove) {
      const formula = remove.closest('[data-js="formula"]');
      if (components(formula).length > 1) {
        remove.closest('[data-js="formula-component"]').remove();
        reindex(formula);
        formula.querySelector('[data-js="formula-add"]').focus();
      }
    }
  });

  document.addEventListener('change', (event) => {
    if (event.target.matches('.rd-msel input[type="checkbox"]')) syncChips(event.target.closest('[data-js="formula-component"]'));
  });

  document.addEventListener('input', (event) => {
    if (!event.target.matches('[data-js="multiselect-filter"]')) return;
    const q = event.target.value.trim().toLowerCase();
    event.target.closest('.rd-msel').querySelectorAll('.rd-msel__opt').forEach((opt) => {
      opt.hidden = q !== '' && !opt.textContent.toLowerCase().includes(q);
    });
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    const list = event.target.closest && event.target.closest('.rd-msel');
    if (!list) return;
    event.preventDefault();
    event.stopPropagation();
    const trigger = document.querySelector(`[aria-controls="${CSS.escape(list.id)}"]`);
    if (trigger) {
      toggleList(trigger, false);
      trigger.focus();
    }
  });
})();
