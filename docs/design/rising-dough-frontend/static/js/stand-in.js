/*
 * STATIC STAND-IN FOR THE SERVER. Delete this file when the templates are wired to FastAPI + HTMX.
 *
 * The base files are static, so nothing can be saved. This script plays the server's part just enough
 * for every control to lead somewhere when you click through the files:
 *
 * - Links into pages/overlays/ open a dialog state page (in the app: hx-get into #modal-root).
 *   The page you came from is remembered; closing, cancelling or saving the dialog takes you back there.
 * - Saving a dialog (any <form> inside a dialog) closes it and shows the "● Saved" flash on the page
 *   you return to (in the app: the POST response swaps the row and adds flash/success out of band).
 * - [data-js="demo-action"] buttons answer like the server would (in the app: hx-post / hx-delete):
 *     data-demo="remove"           hide the row, undo toast "… deleted"
 *     data-demo="remove-selected"  hide the checked rows, undo toast
 *     data-demo="skip"             hide the row, undo toast "… skipped"
 *     data-demo="restore"          hide the row, toast "… restored"
 *     data-demo="retry"            replace the error flash with the success flash
 *     data-demo="toast"            toast with data-demo-label
 * - <form data-demo-next="url">  go to url on submit (sign in, sign out, re-authenticate).
 * - <form data-demo-flash="msg"> show the success flash on submit (settings forms, promote all due).
 * - Any other <form action="#"> outside a dialog does nothing on submit instead of reloading the page.
 * Builds markup with DOM methods only (no innerHTML). No data is fetched.
 */
(() => {
  const KEY_RETURN = 'rd-return';
  const KEY_FLASH = 'rd-flash';
  const store = (() => {
    try {
      const s = window.sessionStorage;
      s.setItem('rd-test', '1');
      s.removeItem('rd-test');
      return s;
    } catch {
      return null;
    }
  })();
  const isOverlayPage = /\/pages\/overlays\//.test(window.location.pathname);

  function svgIcon(name) {
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'rd-icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const use = document.createElementNS(ns, 'use');
    use.setAttribute('href', `#icon-${name}`);
    svg.append(use);
    return svg;
  }

  function toast(message, undo) {
    const root = document.getElementById('toast-root');
    if (!root) return;
    root.querySelectorAll('.rd-toast').forEach((t) => t.remove());
    const el = document.createElement('div');
    el.className = 'rd-toast';
    el.setAttribute('role', 'status');
    el.dataset.js = 'toast';
    const text = document.createElement('span');
    text.textContent = message;
    el.append(text);
    if (undo) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'rd-toast__action';
      btn.textContent = 'undo';
      btn.addEventListener('click', () => {
        undo();
        el.remove();
      });
      el.append(btn);
    }
    root.append(el);
    if (window.RD && window.RD.toast) window.RD.toast.arm(el);
  }

  function flash(message) {
    const region = document.getElementById('flash-region');
    if (!region) return;
    const el = document.createElement('div');
    el.className = 'rd-flash rd-flash--success';
    el.setAttribute('role', 'status');
    const text = document.createElement('span');
    text.textContent = `● ${message}`;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'rd-btn rd-btn--icon rd-flash__close';
    close.setAttribute('aria-label', 'Dismiss');
    close.dataset.js = 'flash-close';
    close.append(svgIcon('close'));
    el.append(text, close);
    region.prepend(el);
  }

  function rowOf(el) {
    return el.closest('.rd-rec') || el.closest('tr, li');
  }

  function hide(rows) {
    rows.forEach((r) => { r.hidden = true; });
    return () => rows.forEach((r) => { r.hidden = false; });
  }

  function closeMenu(el) {
    const pop = el.closest('[popover]');
    if (pop && pop.matches(':popover-open')) pop.hidePopover();
  }

  function demo(btn) {
    const label = btn.dataset.demoLabel || '';
    closeMenu(btn);
    switch (btn.dataset.demo) {
      case 'remove': {
        const row = rowOf(btn);
        if (row) toast(`${label} deleted`, hide([row]));
        break;
      }
      case 'remove-selected': {
        const rows = [...document.querySelectorAll('.rd-check:checked')].map(rowOf).filter(Boolean);
        if (rows.length) toast(`${rows.length} deleted`, hide(rows));
        break;
      }
      case 'skip': {
        const row = rowOf(btn);
        if (row) toast(`${label} skipped`, hide([row]));
        break;
      }
      case 'restore': {
        const row = rowOf(btn);
        if (row) hide([row]);
        toast(`${label} restored`);
        break;
      }
      case 'retry': {
        const f = btn.closest('.rd-flash');
        if (f) f.remove();
        flash(`Saved · ${label}`);
        break;
      }
      default:
        toast(label);
    }
  }

  function goBack(message) {
    const back = store && store.getItem(KEY_RETURN);
    if (message && store) store.setItem(KEY_FLASH, message);
    if (back && back !== window.location.href) {
      store.removeItem(KEY_RETURN);
      window.location.href = back;
      return true;
    }
    if (message) {
      if (store) store.removeItem(KEY_FLASH);
      flash(message);
    }
    return false;
  }

  // Remember where a dialog was opened from.
  document.addEventListener('click', (event) => {
    const link = event.target.closest('a[href]');
    if (link && /\/pages\/overlays\//.test(link.href) && store) {
      if (!(isOverlayPage && store.getItem(KEY_RETURN))) {
        store.setItem(KEY_RETURN, window.location.href.split('#')[0]);
      }
    }
    const btn = event.target.closest('[data-js="demo-action"]');
    if (btn) {
      event.preventDefault();
      demo(btn);
    }
  });

  document.addEventListener('submit', (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.getAttribute('action') !== '#') return;
    event.preventDefault();
    if (form.dataset.demoNext) {
      window.location.href = form.dataset.demoNext;
      return;
    }
    if (form.dataset.demoFlash) {
      flash(form.dataset.demoFlash);
      return;
    }
    const dialog = form.closest('dialog');
    if (dialog) {
      dialog.dataset.demoSaved = '';
      dialog.close('submit');
    }
  });

  // On a dialog state page, closing the dialog returns to the page it was opened from.
  if (isOverlayPage) {
    document.querySelectorAll('#modal-root dialog').forEach((dialog) => {
      dialog.addEventListener('close', () => {
        const saved = dialog.dataset.demoSaved !== undefined;
        delete dialog.dataset.demoSaved;
        goBack(saved ? 'Saved' : '');
      });
    });
  } else {
    document.querySelectorAll('dialog').forEach((dialog) => {
      dialog.addEventListener('close', () => {
        if (dialog.dataset.demoSaved !== undefined) {
          delete dialog.dataset.demoSaved;
          flash('Saved');
        }
      });
    });
  }

  // A flash handed over from the dialog page we just came back from.
  const pending = store && store.getItem(KEY_FLASH);
  if (pending) {
    store.removeItem(KEY_FLASH);
    flash(pending);
  }
})();
