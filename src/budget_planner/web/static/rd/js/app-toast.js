/*
 * App glue for the toast and flash regions (T-UR02, ADR-0143); not part of the vendored handoff.
 *  1. HX-Trigger "toast" (web/htmx.py toast_payload): build the toast in #toast-root.
 *  2. Error responses (404/409/500...) carry only the OOB flash partial (web/errors.py): copy its
 *     content into the matching live region, keeping the region element (id, role, class).
 * Auto-dismiss comes from the vendored toast.js (window.RD.toast.arm), which loads before this module.
 */
(() => {
  function build(detail) {
    const toast = document.createElement('div');
    toast.className = 'rd-toast';
    toast.setAttribute('role', 'status');
    toast.dataset.js = 'toast';
    if (detail.variant) toast.dataset.variant = detail.variant;
    const text = document.createElement('span');
    text.textContent = detail.message || '';
    toast.append(text);
    if (detail.undo_url) {
      const form = document.createElement('form');
      form.method = 'post';
      form.action = detail.undo_url;
      const csrf = document.querySelector('meta[name="csrf-token"]');
      const fields = Object.assign({ _csrf_token: csrf ? csrf.content : '' }, detail.undo_payload || {});
      Object.keys(fields).forEach((key) => {
        const value = fields[key];
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = key;
        input.value = Array.isArray(value) ? value.join(',') : String(value);
        form.append(input);
      });
      const button = document.createElement('button');
      button.type = 'submit';
      button.className = 'rd-toast__action';
      button.textContent = 'undo';
      form.append(button);
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        const body = new FormData(form);
        fetch(detail.undo_url, {
          method: 'POST',
          body: new URLSearchParams(body),
          headers: { 'X-CSRF-Token': String(body.get('_csrf_token')), 'HX-Request': 'true' },
        }).then((response) => {
          toast.remove();
          if (response.ok) window.location.reload();
        });
      });
      toast.append(form);
    }
    return toast;
  }

  document.addEventListener('toast', (event) => {
    const root = document.getElementById('toast-root');
    if (!root) return;
    const toast = build(event.detail || {});
    root.append(toast);
    if (window.RD && window.RD.toast) window.RD.toast.arm(toast);
  });

  /* HX-Trigger "dialog-close" (web/htmx.py Event.DIALOG_CLOSE): a 204 response leaves the confirm dialog
     open, so the server asks the page to close the dialog in #modal-root. */
  document.addEventListener('dialog-close', () => {
    const open = document.querySelector('#modal-root dialog[open]');
    if (open) open.close('cancel');
  });

  const FLASH_OOB = /id="flash-region(-assertive)?"[^>]*hx-swap-oob/;
  /* Same copy as the old shell (static/js/app-init.js) for error bodies that carry no flash. */
  const STATUS_TEXT = {
    400: 'The request was not accepted. Check the form and try again.',
    401: 'Your session has expired. Reload the page and sign in again.',
    403: 'The request was refused. Reload the page and try again.',
    404: 'That item was not found. It may have been removed.',
    409: 'That item changed in the meantime. Reload and try again.',
    503: 'A required service is unavailable. Try again shortly.',
  };
  const FALLBACK_TEXT = 'Something went wrong on our side. Try again.';
  const FORM_RERENDER = [422, 429];

  /* Same markup as fragments/flash/error.html. */
  function flashBox(message) {
    const box = document.createElement('div');
    box.className = 'rd-flash rd-flash--error';
    box.setAttribute('role', 'alert');
    const text = document.createElement('span');
    text.textContent = '\u25b2 ' + message;
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'rd-btn rd-btn--icon rd-flash__close';
    close.setAttribute('aria-label', 'Dismiss');
    close.dataset.js = 'flash-close';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'rd-icon');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '/static/rd/icons/sprite.svg#icon-close');
    svg.append(use);
    close.append(svg);
    box.append(text, close);
    return box;
  }

  /* The shell tells the server which flash markup to send (web/errors.py). */
  document.addEventListener('htmx:configRequest', (event) => {
    if (event.detail && event.detail.headers) event.detail.headers['X-Shell'] = 'rd';
    dropClosedFlashes();
  });

  /* In-dialog flash regions of dialogs that are no longer open are dropped with the next request. */
  function dropClosedFlashes() {
    document.querySelectorAll('dialog:not([open]) [data-flash-in-dialog]').forEach((el) => el.remove());
  }

  /* A dialog that opens again (showModal() sets its `open` attribute) starts without the flash of
     its last session. showModal() fires no event, so one observer on the `open` attribute does it. */
  new MutationObserver((records) => {
    records.forEach((record) => {
      const dialog = record.target;
      if (dialog instanceof HTMLDialogElement && dialog.open) {
        dialog.querySelectorAll('[data-flash-in-dialog]').forEach((el) => el.remove());
      }
    });
  }).observe(document.documentElement, { subtree: true, attributes: true, attributeFilter: ['open'] });

  /* A modal <dialog> sits in the top layer, above #flash-region. While one is open the flash is
     shown in a live region inside the dialog instead (same role and aria-live as the page region),
     created empty first so assistive tech announces the content added next. Dialogs fetched into
     #modal-root are replaced on the next open; others drop it on the next request. */
  function show(id, nodes) {
    dropClosedFlashes();
    const open = document.querySelectorAll('dialog[open]');
    const dialog = open.length ? open[open.length - 1] : null;
    const page = document.getElementById(id);
    if (!dialog) {
      if (page) page.replaceChildren(...nodes);
      return;
    }
    let region = dialog.querySelector('[data-flash-in-dialog="' + id + '"]');
    if (region) {
      region.replaceChildren(...nodes);
      return;
    }
    region = document.createElement('div');
    region.className = 'rd-flash-region';
    region.dataset.flashInDialog = id;
    region.dataset.testid = 'flash-in-dialog';
    region.setAttribute('role', id === 'flash-region-assertive' ? 'alert' : 'status');
    region.setAttribute('aria-live', id === 'flash-region-assertive' ? 'assertive' : 'polite');
    dialog.prepend(region);
    setTimeout(() => region.replaceChildren(...nodes), 0);
  }

  /* New-entry hero refresh (GET /add?hero=1, T-UR07b): the server renders the hero from the values sent
     with the request, so an amount typed while it is in flight would be overwritten. Keep what the user
     typed (value, focus, caret) across the swap. A failed refresh marks the hero stale: the unit shows
     an em dash, because it may no longer match the account select. */
  const HERO = '.rd-dialog__hero';
  let typed = null;
  /* The element whose request failed last: "retry" in the error flash re-issues it. */
  let failedElt = null;

  document.addEventListener('click', (event) => {
    const retry = event.target.closest('[data-js="flash-retry"]');
    if (!retry) return;
    const elt = failedElt;
    const flash = retry.closest('.rd-flash');
    if (flash) flash.remove();
    if (!elt || !elt.isConnected || !window.htmx) return;
    if (elt instanceof HTMLFormElement) elt.requestSubmit();
    else window.htmx.trigger(elt, 'click');
  });

  function isHeroRefresh(detail) {
    const path = (detail.pathInfo && detail.pathInfo.requestPath) || '';
    return detail.target && detail.target.matches && detail.target.matches(HERO) && path.includes('hero=1');
  }

  function markHeroStale() {
    const unit = document.querySelector('#modal-root .rd-dialog__hero .rd-dialog__cur');
    if (unit) unit.textContent = '—';
  }

  document.addEventListener('htmx:beforeSwap', (event) => {
    const detail = event.detail || {};
    if (isHeroRefresh(detail) && !(detail.xhr && detail.xhr.status >= 400)) {
      const input = detail.target.querySelector('input.rd-dialog__amount');
      typed = input
        ? { id: input.id, value: input.value, focus: document.activeElement === input, start: input.selectionStart, end: input.selectionEnd }
        : null;
    }
    const xhr = detail.xhr;
    if (!xhr || xhr.status < 400) return;
    failedElt = detail.elt || null;
    if (String((detail.pathInfo && detail.pathInfo.requestPath) || '').includes('hero=1')) markHeroStale();
    const body = xhr.responseText || '';
    if (FLASH_OOB.test(body)) {
      const incoming = new DOMParser().parseFromString(body, 'text/html');
      ['flash-region', 'flash-region-assertive'].forEach((id) => {
        const from = incoming.getElementById(id);
        const region = document.getElementById(id);
        if (from && region) show(id, Array.from(from.childNodes));
      });
    } else if (!FORM_RERENDER.includes(xhr.status)) {
      const region = document.getElementById('flash-region-assertive');
      if (region) show('flash-region-assertive', [flashBox(STATUS_TEXT[xhr.status] || FALLBACK_TEXT)]);
    } else {
      /* A throttled form (429, T-D18a) re-renders like a 422: the page's own error slot shows the message.
         htmx-csrf.js already lets the 422 through; htmx skips every other 4xx body. */
      if (xhr.status === 429) {
        detail.shouldSwap = true;
        detail.isError = false;
      }
      return;
    }
    detail.shouldSwap = false;
    detail.isError = false;
  });

  /* A save wins over a hero refresh still in flight: the refresh request is aborted when the form
     posts (the refresh element syncs only with itself, so it can never abort or delay the save). */
  document.addEventListener('htmx:beforeRequest', (event) => {
    const detail = event.detail || {};
    if (!detail.elt || detail.elt.tagName !== 'FORM') return;
    const refresh = detail.elt.querySelector('#hero-refresh');
    if (refresh && window.htmx) window.htmx.trigger(refresh, 'htmx:abort');
  });

  let caret = null;

  document.addEventListener('htmx:afterSwap', (event) => {
    const saved = typed;
    typed = null;
    caret = null;
    if (!saved || !event.detail || !event.detail.pathInfo) return;
    if (!String(event.detail.pathInfo.requestPath || '').includes('hero=1')) return;
    const input = document.getElementById(saved.id);
    if (!input || !input.matches('input.rd-dialog__amount')) return;
    input.value = saved.value;
    if (saved.focus && saved.end !== null) {
      /* Refocusing the new input makes amount-input.js select its value a frame later; undo that,
         but only while the value is untouched and fully selected (the user has not acted since). */
      const collapse = () => {
        const whole = input.selectionStart === 0 && input.selectionEnd === input.value.length;
        if (input.value === saved.value && whole && saved.start === saved.end) {
          input.setSelectionRange(saved.end, saved.end);
        }
      };
      input.setSelectionRange(saved.end, saved.end);
      const timer = window.setInterval(collapse, 20);
      window.setTimeout(() => window.clearInterval(timer), 400);
    }
    caret = saved;
  });

  /* htmx restores focus and the old selection while it settles, which can leave the whole amount
     selected (the next keystroke would replace it). Collapse the caret to where it was, after that. */
  document.addEventListener('htmx:afterSettle', () => {
    const saved = caret;
    caret = null;
    if (!saved || !saved.focus) return;
    const place = () => {
      const input = document.getElementById(saved.id);
      if (!input) return;
      input.focus();
      if (saved.end !== null) input.setSelectionRange(saved.end, saved.end);
    };
    place();
    /* amount-input.js selects the value in a frame after every focus: collapse after that frame. */
    window.requestAnimationFrame(() => window.requestAnimationFrame(place));
  });

  /* The category search box is not a form value, but its native change (on blur after a pick) bubbles to
     the picker field and would fire the hero refresh a second time. The picker dispatches its own change. */
  document.addEventListener(
    'change',
    (event) => {
      if (event.target instanceof Element && event.target.matches('[data-js="combobox-input"]')) event.stopPropagation();
    },
    true,
  );

  /* A hero refresh that never got a response (network down) is stale too. */
  document.addEventListener('htmx:sendError', (event) => {
    const path = (event.detail && event.detail.pathInfo && event.detail.pathInfo.requestPath) || '';
    if (path.includes('hero=1')) {
      markHeroStale();
      return;
    }
    /* Inside a form offline.js already shows the offline state (T-UR25); elsewhere the banner replaces the flash. */
    const elt = event.detail && event.detail.elt;
    if (elt instanceof Element && elt.closest('form')) return;
    /* Outside a form offline.js shows the offline banner in #flash-region (same event); the banner
       shows alone, so the assertive flash is raised only if no banner appeared (Q29, T-UR02e). */
    window.setTimeout(() => {
      if (document.querySelector('#flash-region [data-js="offline-state"]')) return;
      show('flash-region-assertive', [flashBox('Could not reach the server. Check your connection and try again.')]);
    }, 0);
  });
})();
