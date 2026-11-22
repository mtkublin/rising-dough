/* T-Q256 — shared CSRF token reader (ADR-0065).
 *
 * Exposes `window.budgetCsrf.token()`: the value of
 * `<meta name="csrf-token">`, or "" when absent. Loaded before htmx-csrf.js
 * and js/passkeys.js so both read the token one way (external file, no
 * inline script: CSP, ADR-0036 §3).
 */
(function () {
  "use strict";

  function token() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return (meta && meta.getAttribute("content")) || "";
  }

  // T-Q289: the token is bound to the session. When a response rotates it (the
  // server echoes the fresh value in `X-CSRF-Token`), refresh the meta tag so the
  // open tab keeps working.
  function adopt(xhr) {
    var fresh = xhr && xhr.getResponseHeader && xhr.getResponseHeader("X-CSRF-Token");
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (fresh && meta) meta.setAttribute("content", fresh);
  }

  document.addEventListener("htmx:afterRequest", function (evt) {
    adopt(evt.detail && evt.detail.xhr);
  });

  window.budgetCsrf = { token: token };
})();
