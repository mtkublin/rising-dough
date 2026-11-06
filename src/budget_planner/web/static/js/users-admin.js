/* T-D17 — /settings/users behaviour (ADR-0073 §2, §3).
 *
 * Static file, no inline script (CSP nonce rules, ADR-0036). Event
 * delegation on document so swapped-in fragments work without rebinding.
 *
 * 1. [data-copy-target] copies the referenced element's text to the clipboard.
 * 2. [data-dismiss-toast] removes the one-shot password toast.
 * 3. 409 responses to requests from the admin panel ([data-users-admin])
 *    are swapped so their out-of-band error flash renders; the server sends
 *    `HX-Reswap: none`, so the main target is left untouched.
 */
(function () {
  "use strict";

  var COPIED_MS = 2000;

  function fallbackCopy(node) {
    var range = document.createRange();
    range.selectNodeContents(node);
    var selection = window.getSelection();
    if (!selection) return false;
    selection.removeAllRanges();
    selection.addRange(range);
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_err) {
      ok = false;
    }
    return ok;
  }

  function markCopied(button, ok) {
    var original = button.dataset.originalLabel || button.textContent;
    button.dataset.originalLabel = original;
    button.textContent = ok ? (button.dataset.copiedLabel || "Copied") : "Press Ctrl+C";
    window.setTimeout(function () {
      button.textContent = original;
    }, COPIED_MS);
  }

  function copyFrom(button) {
    var node = document.querySelector(button.getAttribute("data-copy-target"));
    if (!node) return;
    var text = node.textContent.trim();
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        function () { markCopied(button, true); },
        function () { markCopied(button, fallbackCopy(node)); }
      );
      return;
    }
    markCopied(button, fallbackCopy(node));
  }

  document.addEventListener("click", function (evt) {
    var target = evt.target instanceof Element ? evt.target : null;
    if (!target) return;
    var copyBtn = target.closest("[data-copy-target]");
    if (copyBtn) {
      evt.preventDefault();
      copyFrom(copyBtn);
      return;
    }
    var dismiss = target.closest("[data-dismiss-toast]");
    if (dismiss) {
      evt.preventDefault();
      var toast = dismiss.closest(".rd-password-toast");
      if (toast) toast.remove();
    }
  });

  document.addEventListener("htmx:beforeSwap", function (evt) {
    var detail = evt.detail || {};
    var xhr = detail.xhr;
    var elt = detail.elt;
    if (!xhr || xhr.status !== 409 || !(elt instanceof Element)) return;
    if (!elt.closest("[data-users-admin]")) return;
    detail.shouldSwap = true;
    detail.isError = false;
  });
})();
