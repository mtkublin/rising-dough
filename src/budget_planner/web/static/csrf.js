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

  window.budgetCsrf = { token: token };
})();
